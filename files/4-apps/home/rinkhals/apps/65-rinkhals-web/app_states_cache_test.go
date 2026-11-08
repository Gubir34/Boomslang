package main

import (
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func withFakeAppStatesQuery(t *testing.T, delay time.Duration) *int32 {
	t.Helper()
	var calls int32
	original := runAppStatesQueryFn
	runAppStatesQueryFn = func(ids []string) map[string]appState {
		atomic.AddInt32(&calls, 1)
		time.Sleep(delay)
		out := map[string]appState{}
		for _, id := range ids {
			out[id] = appState{Enabled: true, Running: true}
		}
		return out
	}
	invalidateAppStates()
	t.Cleanup(func() {
		runAppStatesQueryFn = original
		invalidateAppStates()
	})
	return &calls
}

func TestAppStatesAreCachedBetweenPolls(t *testing.T) {
	calls := withFakeAppStatesQuery(t, 0)
	ids := []string{"25-mainsail", "40-moonraker"}

	first := queryAppStates(ids)
	second := queryAppStates(ids)
	if got := atomic.LoadInt32(calls); got != 1 {
		t.Fatalf("expected one shell query for two polls, got %d", got)
	}
	if !first["25-mainsail"].Running || !second["40-moonraker"].Enabled {
		t.Fatalf("unexpected states: %v %v", first, second)
	}
}

func TestInvalidateForcesAFreshQuery(t *testing.T) {
	calls := withFakeAppStatesQuery(t, 0)
	ids := []string{"25-mainsail"}

	queryAppStates(ids)
	invalidateAppStates()
	queryAppStates(ids)
	if got := atomic.LoadInt32(calls); got != 2 {
		t.Fatalf("expected a new query after an app changed, got %d", got)
	}
}

func TestDifferentAppListsAreNotMixedUp(t *testing.T) {
	calls := withFakeAppStatesQuery(t, 0)

	a := queryAppStates([]string{"25-mainsail"})
	b := queryAppStates([]string{"40-moonraker"})
	if got := atomic.LoadInt32(calls); got != 2 {
		t.Fatalf("expected one query per app list, got %d", got)
	}
	if _, ok := b["25-mainsail"]; ok || len(a) != 1 {
		t.Fatalf("cache returned states for the wrong apps: %v %v", a, b)
	}
}

func TestConcurrentPollsShareOneQuery(t *testing.T) {
	calls := withFakeAppStatesQuery(t, 50*time.Millisecond)
	ids := []string{"25-mainsail"}

	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			queryAppStates(ids)
		}()
	}
	wg.Wait()
	if got := atomic.LoadInt32(calls); got != 1 {
		t.Fatalf("expected concurrent polls to share one query, got %d", got)
	}
}

func TestOneQueryServesDifferentSubsets(t *testing.T) {
	calls := withFakeAppStatesQuery(t, 0)

	queryAppStates([]string{"25-mainsail", "40-moonraker", "octoapp"})  // the apps page
	services := queryAppStates([]string{"25-mainsail", "40-moonraker"}) // the dashboard
	one := queryAppStates([]string{"octoapp"})                          // one app's page

	if got := atomic.LoadInt32(calls); got != 1 {
		t.Fatalf("expected one shell query for three overlapping pages, got %d", got)
	}
	if len(services) != 2 || len(one) != 1 || !one["octoapp"].Running {
		t.Fatalf("subsets are wrong: %v %v", services, one)
	}
}

func TestResultOfAQueryThatRacedAChangeIsNotCached(t *testing.T) {
	var calls int32
	started := make(chan struct{})
	release := make(chan struct{})
	original := runAppStatesQueryFn
	runAppStatesQueryFn = func(ids []string) map[string]appState {
		n := atomic.AddInt32(&calls, 1)
		if n == 1 {
			close(started)
			<-release                                                               // the first query is still running when the app changes
			return map[string]appState{"octoapp": {Enabled: false, Running: false}} // pre-change answer
		}
		return map[string]appState{"octoapp": {Enabled: true, Running: true}} // after the change
	}
	invalidateAppStates()
	t.Cleanup(func() { runAppStatesQueryFn = original; invalidateAppStates() })

	done := make(chan struct{})
	go func() { queryAppStates([]string{"octoapp"}); close(done) }()
	<-started
	invalidateAppStates() // the user just started the app
	close(release)
	<-done

	got := queryAppStates([]string{"octoapp"}) // the UI's refetch
	if !got["octoapp"].Running {
		t.Fatalf("the refetch got the stale pre-change state: %v", got)
	}
}

func TestEmptyAnswerIsNotCached(t *testing.T) {
	var calls int32
	original := runAppStatesQueryFn
	runAppStatesQueryFn = func(ids []string) map[string]appState {
		atomic.AddInt32(&calls, 1)
		return map[string]appState{} // a timed out or failed query
	}
	invalidateAppStates()
	t.Cleanup(func() { runAppStatesQueryFn = original; invalidateAppStates() })

	queryAppStates([]string{"octoapp"})
	queryAppStates([]string{"octoapp"})
	if got := atomic.LoadInt32(&calls); got != 2 {
		t.Fatalf("a failed query must be retried, not cached as stopped; got %d queries", got)
	}
}
