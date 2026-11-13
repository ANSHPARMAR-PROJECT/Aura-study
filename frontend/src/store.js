import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export const useTimerStore = create(persist((set, get) => ({
  mode: 'focus',
  durations: { focus: 25, short: 5, long: 15 },
  remainingSeconds: 25 * 60,
  isRunning: false,
  endAt: null,
  sessionStartedAt: null,
  selectedSubjectId: '',
  setSubject: (id) => set({ selectedSubjectId: id || '' }),
  setDurations: (focus, short, long) => set((state) => {
    const durations = { focus, short, long };
    const changed = focus !== state.durations.focus || short !== state.durations.short || long !== state.durations.long;
    // Dashboard refreshes happen after many ordinary actions. Do not reset a
    // paused/partially elapsed timer unless the saved preferences changed.
    const shouldReset = changed && !state.isRunning;
    return { durations, ...(shouldReset ? { remainingSeconds: durations[state.mode] * 60 } : {}) };
  }),
  start: () => {
    const state = get();
    if (state.isRunning || state.remainingSeconds <= 0) return;
    set({
      isRunning: true,
      endAt: Date.now() + state.remainingSeconds * 1000,
      sessionStartedAt: state.sessionStartedAt || (() => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}T${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`; })(),
    });
  },
  pause: () => {
    const state = get();
    if (!state.isRunning) return;
    set({ isRunning: false, remainingSeconds: Math.max(0, Math.ceil((state.endAt - Date.now()) / 1000)), endAt: null });
  },
  reset: (mode = get().mode, duration = 25) => set({
    mode, remainingSeconds: duration * 60, isRunning: false, endAt: null, sessionStartedAt: null,
  }),
  tick: () => {
    let completed = false;
    set((state) => {
      if (!state.isRunning || !state.endAt) return state;
      const remaining = Math.max(0, Math.ceil((state.endAt - Date.now()) / 1000));
      if (remaining <= 0) {
        completed = true;
        return { ...state, isRunning: false, remainingSeconds: 0, endAt: null };
      }
      return { ...state, remainingSeconds: remaining };
    });
    return completed;
  },
  finish: (duration = 25) => set({ isRunning: false, remainingSeconds: duration * 60, endAt: null, sessionStartedAt: null }),
}), {
  name: 'aura-study-timer-v1',
  partialize: (state) => ({
    mode: state.mode, durations: state.durations, remainingSeconds: state.remainingSeconds, isRunning: state.isRunning,
    endAt: state.endAt, sessionStartedAt: state.sessionStartedAt, selectedSubjectId: state.selectedSubjectId,
  }),
}));
