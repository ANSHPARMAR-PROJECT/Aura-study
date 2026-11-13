import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Activity, ArrowDownRight, ArrowRight, BookOpen, CalendarDays, Check, CheckCircle2,
  ChevronDown, CircleHelp, Clock3, Coffee, Download, FileText, FolderKanban, GraduationCap,
  LayoutDashboard, Leaf, Link as LinkIcon, LoaderCircle, LogOut, Menu, MoreHorizontal, Pencil,
  Pause, Play, Plus, RefreshCw, Settings, Sparkles, Target, Trash2, Upload, X, Zap,
  BrainCircuit, Layers, RotateCcw, CalendarCheck, ChevronLeft, ChevronRight,
  Bell, Award, Flame, Trophy, TrendingUp, CalendarClock,
  Users, UserPlus, Send, Copy, Eye, FileDown, ExternalLink, MessageCircle,
} from 'lucide-react';
import { DndContext, useDraggable, useDroppable } from '@dnd-kit/core';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api, setCsrfToken } from './api';
import { useTimerStore } from './store';

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'projects', label: 'My Projects', icon: FolderKanban },
  { id: 'schedule', label: 'Schedule', icon: CalendarDays },
  { id: 'ai', label: 'AI Insights', icon: Sparkles },
  { id: 'resources', label: 'Resource Bank', icon: BookOpen },
  { id: 'groups', label: 'Study Groups', icon: Users },
  { id: 'learning', label: 'Learning Hub', icon: BrainCircuit },
  { id: 'productivity', label: 'Productivity', icon: Activity },
  { id: 'settings', label: 'Settings', icon: Settings },
];

const localDate = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};
const localDateTime = (date, hour, minute = 0) => `${date}T${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
const formatDate = (value) => value ? new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : 'No deadline';
const formatClock = (value) => new Date(value).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
const formatRemaining = (seconds) => `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
const addDaysToIsoDate = (value, days) => {
  const d = new Date(`${value}T12:00:00`);
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};
const calendarExportUrl = (startDate) => {
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Kolkata';
  const params = new URLSearchParams({ start: startDate, end: addDaysToIsoDate(startDate, 90), timezone });
  return `/api/calendar/export?${params.toString()}`;
};

function Toast({ toast, onClose }) {
  useEffect(() => {
    if (!toast) return undefined;
    const timer = setTimeout(onClose, 3400);
    return () => clearTimeout(timer);
  }, [toast, onClose]);
  return <AnimatePresence>{toast && <motion.div className={`toast ${toast.type || 'success'}`} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }}>
    {toast.type === 'error' ? <CircleHelp size={17} /> : <CheckCircle2 size={17} />}
    <span>{toast.message}</span><button aria-label="Dismiss" onClick={onClose}><X size={15} /></button>
  </motion.div>}</AnimatePresence>;
}

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState('login');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ username: '', email: '', identifier: '', password: '' });
  const update = (key, value) => setForm((old) => ({ ...old, [key]: value }));
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      const result = mode === 'login'
        ? await api('/api/login', { method: 'POST', body: { identifier: form.identifier, password: form.password } })
        : await api('/api/register', { method: 'POST', body: { username: form.username, email: form.email, password: form.password } });
      setCsrfToken(result.csrf_token);
      const me = await api('/api/me');
      setCsrfToken(me.csrf_token);
      onAuthenticated(me.user);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <div className="auth-screen">
    <div className="auth-ambient ambient-one" /><div className="auth-ambient ambient-two" />
    <motion.div className="auth-card" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }}>
      <div className="auth-brand"><div className="brand-mark"><Sparkles size={21} /></div><span>AURA <i>Study</i></span></div>
      <div className="auth-kicker">YOUR ACADEMIC RHYTHM</div>
      <h1>{mode === 'login' ? 'Welcome back.' : 'Make space to grow.'}</h1>
      <p className="auth-subtitle">A calmer way to plan, focus, and make progress.</p>
      <div className="auth-tabs"><button className={mode === 'login' ? 'active' : ''} onClick={() => { setMode('login'); setError(''); }}>Sign in</button><button className={mode === 'register' ? 'active' : ''} onClick={() => { setMode('register'); setError(''); }}>Create account</button></div>
      <form onSubmit={submit} className="auth-form">
        {mode === 'register' && <><label>Student username<input value={form.username} onChange={(e) => update('username', e.target.value)} required minLength={3} placeholder="e.g. priya_studies" /></label><label>Email address<input type="email" value={form.email} onChange={(e) => update('email', e.target.value)} required placeholder="you@university.edu" /></label></>}
        {mode === 'login' && <label>Username or email<input value={form.identifier} onChange={(e) => update('identifier', e.target.value)} required placeholder="Your username or email" /></label>}
        <label>Password<input type="password" value={form.password} onChange={(e) => update('password', e.target.value)} required minLength={mode === 'register' ? 8 : 1} placeholder={mode === 'register' ? 'At least 8 characters' : 'Your password'} /></label>
        {error && <div className="form-error">{error}</div>}
        <button className="button button-primary auth-submit" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : null}{mode === 'login' ? 'Enter your workspace' : 'Create my account'}<ArrowRight size={16} /></button>
      </form>
      <div className="auth-foot"><Leaf size={14} /> Small steps, steady growth.</div>
    </motion.div>
  </div>;
}

function FocusTimer({ subjects, onCompleted }) {
  const timer = useTimerStore();
  const [tickLabel, setTickLabel] = useState('Ready when you are');
  const handledRef = useRef(false);
  const durations = timer.durations || { focus: 25, short: 5, long: 15 };
  const progress = timer.mode === 'focus' ? 1 - timer.remainingSeconds / (durations.focus * 60) : 1 - timer.remainingSeconds / (durations[timer.mode] * 60);
  const circumference = 2 * Math.PI * 43;

  useEffect(() => {
    if (!timer.isRunning) return undefined;
    const interval = setInterval(async () => {
      const done = useTimerStore.getState().tick();
      if (done && !handledRef.current) {
        handledRef.current = true;
        const state = useTimerStore.getState();
        const startedAt = state.sessionStartedAt || new Date(Date.now() - durations.focus * 60000).toISOString();
        const sessionKey = `aura-${new Date(startedAt).getTime()}-${state.mode}`;
        try {
          if (state.mode === 'focus') {
            await api('/api/timer/log', { method: 'POST', body: {
              session_key: sessionKey, duration_minutes: durations.focus, started_at: startedAt,
              subject_id: state.selectedSubjectId || null,
            } });
            setTickLabel('Focus session saved');
            onCompleted();
          } else setTickLabel('Break complete. Welcome back.');
        } catch (err) { setTickLabel(err.message); }
        useTimerStore.getState().finish(durations[state.mode] || 25);
        handledRef.current = false;
      }
    }, 500);
    return () => clearInterval(interval);
  }, [timer.isRunning, onCompleted]);

  const chooseMode = (mode) => {
    if (timer.isRunning) timer.pause();
    timer.reset(mode, durations[mode]);
    setTickLabel(mode === 'focus' ? 'Ready when you are' : 'Take a moment to recharge');
  };
  return <section className="timer-card">
    <div className="timer-head"><div><span className="eyebrow eyebrow-light">FOCUS ROOM</span><h3>Find your flow</h3></div><span className="timer-orbit"><Sparkles size={14} /></span></div>
    <div className="timer-modes"><button className={timer.mode === 'focus' ? 'selected' : ''} onClick={() => chooseMode('focus')}>Focus</button><button className={timer.mode === 'short' ? 'selected' : ''} onClick={() => chooseMode('short')}>Short</button><button className={timer.mode === 'long' ? 'selected' : ''} onClick={() => chooseMode('long')}>Long</button></div>
    <div className="timer-ring-wrap"><svg className="timer-ring" viewBox="0 0 100 100" aria-label={`${formatRemaining(timer.remainingSeconds)} remaining`}><circle cx="50" cy="50" r="43" className="ring-track"/><circle cx="50" cy="50" r="43" className="ring-progress" strokeDasharray={circumference} strokeDashoffset={circumference * (1 - Math.max(0, Math.min(1, progress)))} transform="rotate(-90 50 50)" /></svg><div className="timer-digits"><strong>{formatRemaining(timer.remainingSeconds)}</strong><span>{timer.mode === 'focus' ? 'DEEP WORK' : 'RECHARGE'}</span></div></div>
    <select className="timer-course-select" value={timer.selectedSubjectId} onChange={(e) => timer.setSubject(e.target.value)} aria-label="Choose course for focus session"><option value="">Choose a course (optional)</option>{subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
    <div className="timer-controls"><button className="timer-start" onClick={() => { if (timer.isRunning) { timer.pause(); setTickLabel('Paused'); } else { timer.start(); setTickLabel('You are in focus mode'); } }}>{timer.isRunning ? <Pause size={15} fill="currentColor" /> : <Play size={15} fill="currentColor" />}{timer.isRunning ? 'Pause' : 'Start session'}</button><button className="timer-reset" aria-label="Reset timer" onClick={() => { chooseMode(timer.mode); setTickLabel('Timer reset'); }}><RefreshCw size={15} /></button></div>
    <div className="timer-note"><span className={timer.isRunning ? 'pulse-dot' : 'note-dot'} />{tickLabel}</div>
  </section>;
}

function Sidebar({ page, setPage, user, subjects, onLogout, onTimerComplete }) {
  return <aside className="sidebar">
    <div className="brand"><div className="brand-mark"><Sparkles size={20} /></div><div><strong>AURA <i>Study</i></strong><span>STUDENT SPACE</span></div></div>
    <div className="sidebar-label">WORKSPACE</div>
    <nav className="side-nav">{NAV_ITEMS.map(({ id, label, icon: Icon }) => <button key={id} className={page === id ? 'nav-item active' : 'nav-item'} onClick={() => setPage(id)}><Icon size={17} strokeWidth={1.8} /><span>{label}</span>{id === 'ai' && <span className="nav-sparkle"><Sparkles size={12} /></span>}</button>)}</nav>
    <div className="sidebar-divider" />
    <FocusTimer subjects={subjects} onCompleted={onTimerComplete} />
    <div className="sidebar-bottom"><div className="user-avatar">{(user.username || 'S').slice(0, 1).toUpperCase()}</div><div className="user-meta"><strong>{user.username}</strong><span>Student account</span></div><button className="icon-button sidebar-logout" onClick={onLogout} title="Sign out"><LogOut size={16} /></button></div>
  </aside>;
}

function Topbar({ user, stats, page, unreadCount = 0, onNotificationsClick }) {
  const today = new Date();
  const hello = today.getHours() < 12 ? 'Good morning' : today.getHours() < 17 ? 'Good afternoon' : 'Good evening';
  return <header className="topbar"><div><div className="date-line"><span className="date-dot" />{today.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}</div><h1>{page === 'dashboard' ? `${hello}, ${user.username}.` : NAV_ITEMS.find((n) => n.id === page)?.label || 'AURA Study'}</h1><p>{page === 'dashboard' ? 'A little progress, thoughtfully planned.' : 'Make your next study session count.'}</p></div><div className="topbar-right"><div className="daily-goal"><div className="goal-icon"><Target size={17} /></div><div><span>STUDY TIME TODAY</span><strong>{Number(stats.hours_today || 0).toFixed(1)} <small>hrs</small></strong></div></div><button className="topbar-bell" onClick={onNotificationsClick} title="Open notifications" aria-label={`Open notifications, ${unreadCount} unread`}><Bell size={17} />{unreadCount > 0 && <span>{unreadCount > 9 ? '9+' : unreadCount}</span>}</button><div className="date-stamp"><CalendarDays size={16} /><span>{today.toLocaleDateString(undefined, { month: 'short', day: '2-digit' })}</span></div></div></header>;
}

function SectionTitle({ eyebrow, title, action, onAction }) {
  return <div className="section-title"><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div>{action && <button className="text-action" onClick={onAction}>{action}<ArrowRight size={14} /></button>}</div>;
}

function ProjectCard({ project, onEdit, onAddTask, onUpdateTask, onToggleTask, onDeleteTask, onDelete, onAddTag }) {
  const [taskTitle, setTaskTitle] = useState('');
  const [taskDueDate, setTaskDueDate] = useState('');
  const [showTask, setShowTask] = useState(false);
  const [editingTaskId, setEditingTaskId] = useState(null);
  const [taskEditForm, setTaskEditForm] = useState({ title: '', due_date: '' });
  const [tagName, setTagName] = useState('');
  const [showTag, setShowTag] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [editError, setEditError] = useState('');
  const [editForm, setEditForm] = useState({ title: project.title, description: project.description || '', deadline: project.deadline || '' });
  const progress = project.progress_percent || 0;
  return <motion.article className="project-card" layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
    <div className="project-card-top"><div className={`project-icon ${project.color || 'sage'}`}><FolderKanban size={17} /></div><div className="project-card-actions"><button className="icon-button subtle" title="Edit project" onClick={() => { setEditForm({ title: project.title, description: project.description || '', deadline: project.deadline || '' }); setShowEdit((v) => !v); }}><Pencil size={13} /></button><button className="icon-button subtle" title="Delete project" onClick={() => onDelete(project.id)}><Trash2 size={14} /></button></div></div>
    {showEdit && <form className="form-card compact-form project-edit-form" onSubmit={async (e) => { e.preventDefault(); setEditError(''); try { await onEdit(project.id, editForm); setShowEdit(false); } catch (err) { setEditError(err.message); } }}><label>Project name<input required maxLength={180} value={editForm.title} onChange={(e) => setEditForm({ ...editForm, title: e.target.value })} /></label><label>Description<input value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} /></label><label>Deadline<input type="date" value={editForm.deadline} onChange={(e) => setEditForm({ ...editForm, deadline: e.target.value })} /></label>{editError && <div className="form-error">{editError}</div>}<div className="form-actions"><button className="button button-dark" type="submit">Save changes</button><button type="button" className="button button-quiet" onClick={() => setShowEdit(false)}>Cancel</button></div></form>}
    <div className="project-title-row"><h3>{project.title}</h3><span className="project-deadline">{project.deadline ? formatDate(project.deadline) : 'No deadline'}</span></div>
    {project.description && <p className="project-description">{project.description}</p>}
    {project.tags?.length > 0 && <div className="project-tags">{project.tags.map((tag) => <span className={`tag-pill ${tag.color || 'sage'}`} key={tag.id}>{tag.name}</span>)}</div>}
    <div className="progress-meta"><span>Progress</span><strong>{progress}%</strong></div><div className="progress-track"><div className={`progress-fill ${project.color || 'sage'}`} style={{ width: `${progress}%` }} /></div>
    <div className="task-list">{project.tasks?.map((task) => <div key={task.id} className={`task-item ${task.status === 'done' ? 'done' : ''}`}>
      {editingTaskId === task.id ? <form className="task-edit-form" onSubmit={async (e) => { e.preventDefault(); try { await onUpdateTask(task.id, taskEditForm); setEditingTaskId(null); } catch { /* Toast is displayed by the page handler. */ } }}>
        <input aria-label="Task title" required maxLength={180} value={taskEditForm.title} onChange={(e) => setTaskEditForm({ ...taskEditForm, title: e.target.value })} />
        <input aria-label="Task due date" type="date" value={taskEditForm.due_date} onChange={(e) => setTaskEditForm({ ...taskEditForm, due_date: e.target.value })} />
        <button className="icon-button subtle" type="submit" title="Save task"><Check size={13} /></button>
        <button className="icon-button subtle" type="button" title="Cancel" onClick={() => setEditingTaskId(null)}><X size={13} /></button>
      </form> : <>
        <label className={`task-line ${task.status === 'done' ? 'done' : ''}`}><input type="checkbox" checked={task.status === 'done'} onChange={() => onToggleTask(task)} /><span>{task.title}</span></label>
        {task.due_date && <small className="task-due">Due {formatDate(task.due_date)}</small>}
        <div className="task-actions"><button className="icon-button subtle" title="Edit task" onClick={() => { setEditingTaskId(task.id); setTaskEditForm({ title: task.title, due_date: task.due_date || '' }); }}><Pencil size={12} /></button><button className="icon-button subtle" title="Delete task" onClick={() => onDeleteTask(task.id)}><Trash2 size={12} /></button></div>
      </>}
    </div>)}</div>
    <button className="add-task-link" onClick={() => setShowTag((v) => !v)}><Plus size={13} />Add tag</button>
    {showTag && <form className="inline-add" onSubmit={async (e) => { e.preventDefault(); if (tagName.trim()) { await onAddTag(project.id, tagName.trim()); setTagName(''); setShowTag(false); } }}><input autoFocus value={tagName} onChange={(e) => setTagName(e.target.value)} placeholder="Tag name" /><button type="submit"><Check size={14} /></button><button type="button" onClick={() => setShowTag(false)}><X size={14} /></button></form>}
    {showTask ? <form className="inline-add task-add-form" onSubmit={async (e) => { e.preventDefault(); if (taskTitle.trim()) { await onAddTask(project.id, { title: taskTitle.trim(), due_date: taskDueDate || null }); setTaskTitle(''); setTaskDueDate(''); setShowTask(false); } }}><input autoFocus value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)} placeholder="New task name" /><input type="date" aria-label="Task due date" value={taskDueDate} onChange={(e) => setTaskDueDate(e.target.value)} /><button type="submit" title="Add task"><Check size={14} /></button><button type="button" title="Cancel" onClick={() => setShowTask(false)}><X size={14} /></button></form> : <button className="add-task-link" onClick={() => setShowTask(true)}><Plus size={13} /> Add a task</button>}
  </motion.article>;
}

function ProjectsPanel({ projects, onCreateProject, onEditProject, onAddTask, onUpdateTask, onToggleTask, onDeleteTask, onDeleteProject, onAddTag, subjects, onCreateCourse, onUpdateCourse, onDeleteCourse }) {
  const [showProjectForm, setShowProjectForm] = useState(false);
  const [showCourseForm, setShowCourseForm] = useState(false);
  const [projectForm, setProjectForm] = useState({ title: '', description: '', deadline: '' });
  const [courseForm, setCourseForm] = useState({ name: '', exam_date: '', difficulty: '3', target_hours: '12' });
  const [courseError, setCourseError] = useState('');
  const [editingCourseId, setEditingCourseId] = useState(null);
  const [courseEditForm, setCourseEditForm] = useState({ name: '', exam_date: '', difficulty: '3', target_hours: '12' });
  return <div className="panel-column">
    <section className="panel project-panel"><SectionTitle eyebrow="WHAT YOU'RE BUILDING" title="My Projects" action="New project" onAction={() => setShowProjectForm((v) => !v)} />
      {showProjectForm && <form className="form-card compact-form" onSubmit={async (e) => { e.preventDefault(); await onCreateProject(projectForm); setProjectForm({ title: '', description: '', deadline: '' }); setShowProjectForm(false); }}><label>Project name<input required value={projectForm.title} onChange={(e) => setProjectForm({ ...projectForm, title: e.target.value })} placeholder="e.g. Psychology thesis" /></label><label>Short description<input value={projectForm.description} onChange={(e) => setProjectForm({ ...projectForm, description: e.target.value })} placeholder="What are you working toward?" /></label><label>Deadline<input type="date" value={projectForm.deadline} onChange={(e) => setProjectForm({ ...projectForm, deadline: e.target.value })} /></label><div className="form-actions"><button className="button button-dark" type="submit">Save project</button><button type="button" className="button button-quiet" onClick={() => setShowProjectForm(false)}>Cancel</button></div></form>}
      {projects.length ? <div className="project-list">{projects.map((p) => <ProjectCard key={p.id} project={p} onEdit={onEditProject} onAddTask={onAddTask} onUpdateTask={onUpdateTask} onToggleTask={onToggleTask} onDeleteTask={onDeleteTask} onDelete={onDeleteProject} onAddTag={onAddTag} />)}</div> : <EmptyState icon={FolderKanban} title="Your next big thing starts here" text="Create a project and break it into small, finishable tasks." />}
    </section>
    <section className="panel course-panel"><SectionTitle eyebrow="YOUR LEARNING LIST" title="Enrolled courses" action={showCourseForm ? 'Close' : 'Add course'} onAction={() => setShowCourseForm((v) => !v)} />
      {showCourseForm && <form className="form-card compact-form" onSubmit={async (e) => { e.preventDefault(); setCourseError(''); try { await onCreateCourse(courseForm); setCourseForm({ name: '', exam_date: '', difficulty: '3', target_hours: '12' }); setShowCourseForm(false); } catch (err) { setCourseError(err.message); } }}><label>Course title<input required value={courseForm.name} onChange={(e) => setCourseForm({ ...courseForm, name: e.target.value })} placeholder="e.g. Operating Systems" /></label><div className="form-two"><label>Exam date<input type="date" required value={courseForm.exam_date} onChange={(e) => setCourseForm({ ...courseForm, exam_date: e.target.value })} /></label><label>Difficulty<select value={courseForm.difficulty} onChange={(e) => setCourseForm({ ...courseForm, difficulty: e.target.value })}><option value="1">Minimal</option><option value="2">Moderate</option><option value="3">Standard</option><option value="4">High</option><option value="5">Extreme</option></select></label></div><label>Target hours<input type="number" min="1" step="0.5" value={courseForm.target_hours} onChange={(e) => setCourseForm({ ...courseForm, target_hours: e.target.value })} /></label>{courseError && <div className="form-error">{courseError}</div>}<button className="button button-dark" type="submit">Save course</button></form>}
      {subjects.length ? <div className="course-list">{subjects.map((s) => { const pct = Math.min(100, Math.round((s.completed_hours / s.target_hours) * 100)); return <div className="course-row course-row-wrap" key={s.id}>
        {editingCourseId === s.id ? <form className="form-card compact-form course-edit-form" onSubmit={async (e) => { e.preventDefault(); setCourseError(''); try { await onUpdateCourse(s.id, courseEditForm); setEditingCourseId(null); } catch (err) { setCourseError(err.message); } }}>
          <label>Course title<input required maxLength={180} value={courseEditForm.name} onChange={(e) => setCourseEditForm({ ...courseEditForm, name: e.target.value })} /></label>
          <div className="form-two"><label>Exam date<input type="date" required value={courseEditForm.exam_date} onChange={(e) => setCourseEditForm({ ...courseEditForm, exam_date: e.target.value })} /></label><label>Difficulty<select value={courseEditForm.difficulty} onChange={(e) => setCourseEditForm({ ...courseEditForm, difficulty: e.target.value })}><option value="1">Minimal</option><option value="2">Moderate</option><option value="3">Standard</option><option value="4">High</option><option value="5">Extreme</option></select></label></div>
          <label>Target hours<input type="number" min="1" step="0.5" value={courseEditForm.target_hours} onChange={(e) => setCourseEditForm({ ...courseEditForm, target_hours: e.target.value })} /></label>
          {courseError && <div className="form-error">{courseError}</div>}<div className="form-actions"><button className="button button-dark" type="submit">Save course</button><button className="button button-quiet" type="button" onClick={() => setEditingCourseId(null)}>Cancel</button></div>
        </form> : <><div className="course-symbol"><BookOpen size={15} /></div><div className="course-main"><div className="course-name-line"><strong>{s.name}</strong><div className="course-actions"><button className="icon-button subtle" onClick={() => { setCourseEditForm({ name: s.name, exam_date: s.exam_date, difficulty: String(s.difficulty), target_hours: String(s.target_hours) }); setCourseError(''); setEditingCourseId(s.id); }} title="Edit course"><Pencil size={13} /></button><button className="icon-button subtle" onClick={() => onDeleteCourse(s.id)} title="Delete course"><Trash2 size={13} /></button></div></div><div className="course-subline">Exam {formatDate(s.exam_date)} · {Number(s.completed_hours).toFixed(1)} / {Number(s.target_hours).toFixed(1)} hrs</div><div className="progress-track slim"><div className="progress-fill sage" style={{ width: `${pct}%` }} /></div></div><span className="course-percent">{pct}%</span></>}
      </div>; })}</div> : <div className="mini-empty">No courses yet. Add a course to connect study time with exam goals.</div>}
    </section>
  </div>;
}

function EmptyState({ icon: Icon, title, text }) { return <div className="empty-state"><div className="empty-icon"><Icon size={20} /></div><strong>{title}</strong><p>{text}</p></div>; }

function SchedulePanel({ events, projects, subjects, onCreateEvent, onUpdateEvent, onDeleteEvent, onManualLog, onReload, selectedDate, onDateChange }) {
  const [showForm, setShowForm] = useState(false);
  const [showLogForm, setShowLogForm] = useState(false);
  const [editingEventId, setEditingEventId] = useState(null);
  const today = localDate();
  const [eventForm, setEventForm] = useState({ title: '', start_time: localDateTime(selectedDate, 10), end_time: localDateTime(selectedDate, 11), project_id: '', subject_id: '', event_type: 'study' });
  const [logForm, setLogForm] = useState({ subject_id: '', hours: '1', log_date: today });
  useEffect(() => {
    if (!editingEventId) setEventForm((current) => ({ ...current, start_time: localDateTime(selectedDate, 10), end_time: localDateTime(selectedDate, 11) }));
  }, [selectedDate]);
  const [error, setError] = useState('');
  const { setNodeRef, isOver } = useDroppable({ id: 'schedule-drop-zone' });
  const sorted = [...events].sort((a, b) => new Date(a.start_time) - new Date(b.start_time));
  return <div className="panel-column">
    <section className={`panel schedule-panel ${isOver ? 'drop-active' : ''}`} ref={setNodeRef}>
      <SectionTitle eyebrow="MAKE ROOM FOR WHAT MATTERS" title={selectedDate === today ? "Today's schedule" : "Schedule"} action={showForm ? 'Close' : 'Add block'} onAction={() => setShowForm((v) => !v)} />
      <div className="schedule-date-row"><label className="schedule-date-picker"><CalendarDays size={14} /><input type="date" value={selectedDate} onChange={(e) => onDateChange(e.target.value)} aria-label="Choose schedule date" /></label><span className="timezone-note">LOCAL TIME</span></div>
      {showForm && <form className="form-card compact-form" onSubmit={async (e) => { e.preventDefault(); setError(''); try { await onCreateEvent({ ...eventForm, project_id: eventForm.project_id || null, subject_id: eventForm.subject_id || null }); setShowForm(false); setEventForm({ ...eventForm, title: '' }); } catch (err) { setError(err.message); } }}><label>Block title<input required value={eventForm.title} onChange={(e) => setEventForm({ ...eventForm, title: e.target.value })} placeholder="e.g. Literature review" /></label><div className="form-two"><label>Starts<input type="datetime-local" value={eventForm.start_time} onChange={(e) => setEventForm({ ...eventForm, start_time: e.target.value })} required /></label><label>Ends<input type="datetime-local" value={eventForm.end_time} onChange={(e) => setEventForm({ ...eventForm, end_time: e.target.value })} required /></label></div><label>Block type<select value={eventForm.event_type || 'study'} onChange={(e) => setEventForm({ ...eventForm, event_type: e.target.value })}><option value="study">Focused study</option><option value="break">Recharge break</option><option value="personal">Personal block</option></select></label><label>Link to project (optional)<select value={eventForm.project_id} onChange={(e) => setEventForm({ ...eventForm, project_id: e.target.value })}><option value="">No project</option>{projects.map((p) => <option value={p.id} key={p.id}>{p.title}</option>)}</select></label><label>Related course (optional)<select value={eventForm.subject_id} onChange={(e) => setEventForm({ ...eventForm, subject_id: e.target.value })}><option value="">No course</option>{subjects.map((subject) => <option value={subject.id} key={subject.id}>{subject.name}</option>)}</select></label>{error && <div className="form-error">{error}</div>}<button className="button button-dark" type="submit">Save schedule block</button></form>}
      {editingEventId && <form className="form-card compact-form event-edit-form" onSubmit={async (e) => { e.preventDefault(); setError(''); try { await onUpdateEvent(editingEventId, { ...eventForm, project_id: eventForm.project_id || null, subject_id: eventForm.subject_id || null }); setEditingEventId(null); } catch (err) { setError(err.message); } }}>
        <div className="edit-form-heading"><strong>Edit schedule block</strong><button type="button" className="icon-button subtle" onClick={() => setEditingEventId(null)} aria-label="Close editor"><X size={14} /></button></div>
        <label>Block title<input required value={eventForm.title} onChange={(e) => setEventForm({ ...eventForm, title: e.target.value })} /></label>
        <div className="form-two"><label>Starts<input type="datetime-local" required value={eventForm.start_time} onChange={(e) => setEventForm({ ...eventForm, start_time: e.target.value })} /></label><label>Ends<input type="datetime-local" required value={eventForm.end_time} onChange={(e) => setEventForm({ ...eventForm, end_time: e.target.value })} /></label></div>
        <label>Block type<select value={eventForm.event_type || 'study'} onChange={(e) => setEventForm({ ...eventForm, event_type: e.target.value })}><option value="study">Focused study</option><option value="break">Recharge break</option><option value="personal">Personal block</option></select></label>
        <label>Project (optional)<select value={eventForm.project_id || ''} onChange={(e) => setEventForm({ ...eventForm, project_id: e.target.value })}><option value="">No project</option>{projects.map((p) => <option value={p.id} key={p.id}>{p.title}</option>)}</select></label>
        <label>Course (optional)<select value={eventForm.subject_id || ''} onChange={(e) => setEventForm({ ...eventForm, subject_id: e.target.value })}><option value="">No course</option>{subjects.map((s) => <option value={s.id} key={s.id}>{s.name}</option>)}</select></label>
        {error && <div className="form-error">{error}</div>}<div className="form-actions"><button className="button button-dark" type="submit">Save changes</button><button type="button" className="button button-quiet" onClick={() => setEditingEventId(null)}>Cancel</button></div>
      </form>}
      <div className="timeline-list">{sorted.length ? sorted.map((event) => <div className={`timeline-event ${event.color || 'lavender'}`} key={event.id}><div className="event-time">{formatClock(event.start_time)}<span>{formatClock(event.end_time)}</span></div><div className="event-line"><span /></div><div className="event-body"><strong>{event.title}</strong><span>{event.event_type === 'break' ? 'Recharge break' : event.event_type === 'study' ? 'Focused study' : 'Personal block'}</span></div><div className="event-actions"><button className="icon-button subtle" title="Edit event" onClick={() => { setEventForm({ title: event.title, start_time: event.start_time.slice(0, 16), end_time: event.end_time.slice(0, 16), project_id: event.project_id || '', subject_id: event.subject_id || '', event_type: event.event_type || 'study' }); setEditingEventId(event.id); setShowForm(false); setError(''); }}><Pencil size={12} /></button><button className="icon-button subtle event-delete" title="Remove event" onClick={() => onDeleteEvent(event.id)}><Trash2 size={13} /></button></div></div>) : <EmptyState icon={CalendarDays} title="A clear page for today" text="Add a study block, or drag an AI suggestion here to make a plan." />}</div>
      {isOver && <div className="drop-hint"><Plus size={14} />Drop to add this recommendation to your timeline</div>}
      <div className="schedule-footer schedule-footer-expanded">
        <button className="text-action" onClick={() => setShowLogForm((v) => !v)}><Plus size={14} />Log study hours</button>
        <div className="calendar-export-actions">
          <a className="text-action" href={calendarExportUrl(selectedDate)} title="Download the next 90 days as an iCalendar file"><Download size={13} />Export .ics</a>
          <a className="text-action" href="https://calendar.google.com/calendar/u/0/r/settings/importandexport" target="_blank" rel="noreferrer"><ExternalLink size={12} />Google Calendar</a>
        </div>
        <button className="icon-button subtle" onClick={onReload} title="Refresh schedule"><RefreshCw size={14} /></button>
      </div>
      <p className="calendar-export-note">Import the .ics file into Google Calendar, Outlook, or Apple Calendar. Export is a one-way snapshot; it does not sync changes automatically.</p>
      {showLogForm && <form className="form-card compact-form" onSubmit={async (e) => { e.preventDefault(); setError(''); try { await onManualLog(logForm); setShowLogForm(false); } catch (err) { setError(err.message); } }}><label>Course<select required value={logForm.subject_id} onChange={(e) => setLogForm({ ...logForm, subject_id: e.target.value })}><option value="">Choose a course</option>{subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label><div className="form-two"><label>Hours<input type="number" min="0.25" max="24" step="0.25" required value={logForm.hours} onChange={(e) => setLogForm({ ...logForm, hours: e.target.value })} /></label><label>Date<input type="date" required value={logForm.log_date} onChange={(e) => setLogForm({ ...logForm, log_date: e.target.value })} /></label></div>{error && <div className="form-error">{error}</div>}<button className="button button-dark" type="submit">Save study log</button></form>}
    </section>
    <StudyChart subjects={subjects} />
  </div>;
}

function StudyChart({ subjects }) {
  const chartData = subjects.slice(0, 5).map((s) => ({ name: s.name.length > 12 ? `${s.name.slice(0, 11)}…` : s.name, Logged: Number(s.completed_hours), Goal: Number(s.target_hours) }));
  return <section className="panel chart-panel"><SectionTitle eyebrow="YOUR EFFORT, MADE VISIBLE" title="Course progress" />{chartData.length ? <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><BarChart data={chartData} margin={{ top: 5, right: 4, left: -22, bottom: 0 }} barGap={4}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#ebe9e1" /><XAxis dataKey="name" tick={{ fill: '#7d8177', fontSize: 10 }} axisLine={false} tickLine={false} /><YAxis tick={{ fill: '#7d8177', fontSize: 10 }} axisLine={false} tickLine={false} /><Tooltip contentStyle={{ borderRadius: 12, border: '1px solid #e9e5dc', fontSize: 12 }} /><Bar dataKey="Logged" fill="#557b61" radius={[5, 5, 0, 0]} /><Bar dataKey="Goal" fill="#e4d8fa" radius={[5, 5, 0, 0]} /></BarChart></ResponsiveContainer></div> : <div className="mini-empty">Add a course to see your study progress here.</div>}</section>;
}

function DraggableRecommendation({ card, onAdd }) {
  const canSchedule = Boolean(card.suggested_start_time);
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: `recommendation-${card.type}`, data: { card }, disabled: !canSchedule });
  const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined;
  const Icon = card.type === 'focus' ? Zap : card.type === 'recharge' ? Coffee : Target;
  return <motion.article ref={setNodeRef} style={style} className={`ai-card ai-${card.type} ${isDragging ? 'dragging' : ''}`} layout>
    <div className="ai-card-top"><span className="ai-icon"><Icon size={15} /></span><span>{card.title}</span><button className="drag-handle" title="Drag to schedule" {...listeners} {...attributes}><MoreHorizontal size={16} /></button></div>
    <h3>{card.headline}</h3><p>{card.description}</p>
    <button className="ai-action" onClick={() => onAdd(card)} disabled={!canSchedule} title={canSchedule ? 'Add this suggestion to your schedule' : 'No matching open slot in the planning window'}><Plus size={14} />{canSchedule ? (card.type === 'recharge' ? 'Plan a break' : card.type === 'focus' ? 'Plan a focus block' : 'Add to timeline') : 'No open time slot'}</button>
  </motion.article>;
}

function AIHub({ recommendations, onAdd, onRefresh, page = 'dashboard' }) {
  const cards = recommendations?.cards || [];
  return <section className={`ai-hub ${page === 'ai' ? 'ai-hub-page' : ''}`}>
    <div className="ai-hub-glow" /><div className="ai-hub-head"><div className="ai-brand-line"><div className="ai-spark"><Sparkles size={16} /></div><span className="eyebrow eyebrow-light">YOUR PERSONAL STUDY COACH</span></div><button className="ai-refresh" onClick={onRefresh} title="Refresh recommendations"><RefreshCw size={14} /></button></div>
    <h2>AI Insight Hub</h2><p className="ai-intro">Small, thoughtful nudges for a more focused day.</p>
    <div className="ai-engine-pill"><span className="pulse-dot" />{recommendations?.engine || 'AURA is thinking'}</div>
    <div className="ai-cards">{cards.length ? cards.map((card) => <DraggableRecommendation key={card.type} card={card} onAdd={onAdd} />) : <div className="ai-empty">Add a course to unlock your first tailored study insight.</div>}</div>
    {recommendations?.daily_plan?.length > 0 && <div className="daily-plan"><div className="daily-plan-title">TODAY'S STUDY ALLOCATION</div>{recommendations.daily_plan.slice(0, 3).map((item) => <div className="daily-plan-row" key={item.subject_id || item.subject}><span>{item.subject}</span><strong>{item.suggested_hours}h</strong></div>)}</div>}
    <div className="ai-footnote"><Leaf size={14} /><span>Recommendations improve as you log study sessions.</span></div>
  </section>;
}

function ResourceBank({ projects, onRefresh, onDelete, showToast }) {
  const [resources, setResources] = useState([]);
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('notes');
  const [url, setUrl] = useState('');
  const [projectId, setProjectId] = useState('');
  const [file, setFile] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({ title: '', description: '', category: 'other', project_id: '' });
  const [preview, setPreview] = useState(null);
  const load = useCallback(async () => { try { setResources(await api('/api/resources')); setError(''); } catch (err) { setError(err.message); } }, []);
  useEffect(() => { load(); }, [load]);
  const visibleResources = resources.filter((resource) => {
    const matchesSearch = `${resource.title} ${resource.original_filename || ''} ${resource.resource_type} ${resource.description || ''}`.toLowerCase().includes(search.toLowerCase());
    return matchesSearch && (categoryFilter === 'all' || resource.category === categoryFilter);
  });
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      const body = new FormData(); body.append('title', title); body.append('description', description); body.append('category', category);
      if (url) body.append('url', url); if (file) body.append('file', file); if (projectId) body.append('project_id', projectId);
      await api('/api/resources', { method: 'POST', body });
      setTitle(''); setDescription(''); setCategory('notes'); setUrl(''); setFile(null); setProjectId(''); e.target.reset();
      await load(); showToast?.('Resource saved to your library');
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function saveEdit(e) {
    e.preventDefault();
    try {
      await api(`/api/resources/${editingId}`, { method: 'PATCH', body: { ...editForm, project_id: editForm.project_id || null } });
      setEditingId(null); await load(); showToast?.('Resource details updated');
    } catch (err) { setError(err.message); }
  }
  const formatBytes = (bytes) => bytes ? bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB` : 'Link';
  const categoryLabel = (value) => ({ notes: 'Notes', lecture: 'Lecture', textbook: 'Textbook', assignment: 'Assignment', research: 'Research', reference: 'Reference', other: 'Other' }[value] || 'Other');
  return <div className="resource-page phase4-resource-page">
    <section className="panel resource-create">
      <SectionTitle eyebrow="KEEP GOOD MATERIAL CLOSE" title="Resource Bank" />
      <p className="panel-description">Organize readings, lecture slides, project files, and useful links. Preview PDFs and images without leaving AURA.</p>
      <form className="resource-form" onSubmit={submit}>
        <label>Resource title<input required maxLength={180} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Research methodology notes" /></label>
        <label>Description (optional)<textarea rows={2} maxLength={2000} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="A short note about this material" /></label>
        <label>Category<select value={category} onChange={(e) => setCategory(e.target.value)}><option value="notes">Notes</option><option value="lecture">Lecture</option><option value="textbook">Textbook</option><option value="assignment">Assignment</option><option value="research">Research</option><option value="reference">Reference</option><option value="other">Other</option></select></label>
        <div className="form-two"><label>Attach a file<input type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.txt,.md,.png,.jpg,.jpeg,.webp" onChange={(e) => { setFile(e.target.files?.[0] || null); if (e.target.files?.[0]) setUrl(''); }} /></label><label>Or add a web link<input type="url" value={url} onChange={(e) => { setUrl(e.target.value); if (e.target.value) setFile(null); }} placeholder="https://..." /></label></div>
        <label>Related project (optional)<select value={projectId} onChange={(e) => setProjectId(e.target.value)}><option value="">General resource</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}</select></label>
        {error && <div className="form-error">{error}</div>}
        <button className="button button-dark" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <Plus size={15} />}Save resource</button>
        <small className="field-hint">Files up to 10 MB. PDF and images can be previewed; Office and text files can be downloaded.</small>
      </form>
    </section>
    <section className="panel resource-list-panel">
      <SectionTitle eyebrow="YOUR PERSONAL LIBRARY" title={`${resources.length} saved resources`} action="Refresh" onAction={load} />
      <div className="resource-filter-row"><input className="resource-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search title, filename, or description…" /><select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} aria-label="Filter resource category"><option value="all">All categories</option><option value="notes">Notes</option><option value="lecture">Lecture</option><option value="textbook">Textbook</option><option value="assignment">Assignment</option><option value="research">Research</option><option value="reference">Reference</option><option value="other">Other</option></select></div>
      {visibleResources.length ? <div className="resource-list">{visibleResources.map((r) => <div className="resource-row resource-row-rich" key={r.id}>
        <div className="resource-icon">{r.resource_type === 'link' ? <LinkIcon size={17} /> : <FileText size={17} />}</div>
        <div className="resource-details"><strong>{r.title}</strong><span>{r.original_filename || (r.url ? (() => { try { return new URL(r.url).hostname; } catch { return r.url; } })() : r.resource_type)} · {categoryLabel(r.category)} · {formatBytes(r.file_size)}</span>{r.description && <small>{r.description}</small>}</div>
        <div className="resource-actions">
          {r.preview_url && <button className="icon-button" onClick={() => setPreview(r)} title="Preview resource"><Eye size={15} /></button>}
          {r.download_url ? <a className="icon-button" href={r.download_url} title="Download"><Download size={15} /></a> : <a className="icon-button" href={r.url} target="_blank" rel="noreferrer" title="Open link"><ArrowRight size={15} /></a>}
          <button className="icon-button" onClick={() => { setEditingId(r.id); setEditForm({ title: r.title, description: r.description || '', category: r.category || 'other', project_id: r.project_id || '' }); setError(''); }} title="Edit resource"><Pencil size={14} /></button>
          <button className="icon-button subtle" onClick={() => onDelete(r.id, load)} title="Delete resource"><Trash2 size={14} /></button>
        </div>
        {editingId === r.id && <form className="resource-edit-form" onSubmit={saveEdit}><label>Title<input required maxLength={180} value={editForm.title} onChange={(e) => setEditForm({ ...editForm, title: e.target.value })} /></label><label>Description<textarea rows={2} maxLength={2000} value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} /></label><div className="form-two"><label>Category<select value={editForm.category} onChange={(e) => setEditForm({ ...editForm, category: e.target.value })}><option value="notes">Notes</option><option value="lecture">Lecture</option><option value="textbook">Textbook</option><option value="assignment">Assignment</option><option value="research">Research</option><option value="reference">Reference</option><option value="other">Other</option></select></label><label>Project<select value={editForm.project_id} onChange={(e) => setEditForm({ ...editForm, project_id: e.target.value })}><option value="">General resource</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.title}</option>)}</select></label></div><div className="form-actions"><button className="button button-dark" type="submit">Save details</button><button className="button button-quiet" type="button" onClick={() => setEditingId(null)}>Cancel</button></div></form>}
      </div>)}</div> : <EmptyState icon={BookOpen} title={resources.length ? 'No matching resources' : 'Your library is ready'} text={resources.length ? 'Try another search or category.' : 'Save a file or a useful link to build your personal resource bank.'} />}
    </section>
    {preview && <div className="resource-preview-backdrop" role="presentation" onClick={() => setPreview(null)}><section className="resource-preview-modal" role="dialog" aria-modal="true" aria-label={`Preview ${preview.title}`} onClick={(e) => e.stopPropagation()}><div className="resource-preview-head"><div><span className="eyebrow">RESOURCE PREVIEW</span><h2>{preview.title}</h2></div><button className="icon-button" onClick={() => setPreview(null)} aria-label="Close preview"><X size={18} /></button></div>{['png', 'jpg', 'jpeg', 'webp'].includes(preview.resource_type) ? <img className="resource-preview-image" src={preview.preview_url} alt={preview.title} /> : <iframe className="resource-preview-frame" src={preview.preview_url} title={`Preview ${preview.title}`} />}</section></div>}
  </div>;
}

function StudyGroupsPage({ showToast }) {
  const [groups, setGroups] = useState([]);
  const [selectedGroupId, setSelectedGroupId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [resources, setResources] = useState([]);
  const [groupName, setGroupName] = useState('');
  const [groupDescription, setGroupDescription] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const [message, setMessage] = useState('');
  const [shareResourceId, setShareResourceId] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const loadDetail = useCallback(async (id) => {
    try { setDetail(await api(`/api/groups/${id}`)); setError(''); }
    catch (err) { setDetail(null); setError(err.message); }
  }, []);
  const loadGroups = useCallback(async () => {
    try {
      const rows = await api('/api/groups');
      setGroups(rows);
      if (!selectedGroupId && rows.length) setSelectedGroupId(rows[0].id);
      if (selectedGroupId && !rows.some((group) => group.id === selectedGroupId)) { setSelectedGroupId(rows[0]?.id || null); setDetail(null); }
    } catch (err) { setError(err.message); }
  }, [selectedGroupId]);
  useEffect(() => { loadGroups(); api('/api/resources').then(setResources).catch(() => setResources([])); }, [loadGroups]);
  useEffect(() => { if (selectedGroupId) loadDetail(selectedGroupId); else setDetail(null); }, [selectedGroupId, loadDetail]);

  async function createGroup(e) {
    e.preventDefault(); setBusy(true); setError('');
    try { const result = await api('/api/groups', { method: 'POST', body: { name: groupName, description: groupDescription } }); setGroupName(''); setGroupDescription(''); await loadGroups(); setSelectedGroupId(result.group.id); showToast?.('Study group created'); }
    catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  async function joinGroup(e) {
    e.preventDefault(); setBusy(true); setError('');
    try { const result = await api('/api/groups/join', { method: 'POST', body: { invite_code: inviteCode } }); setInviteCode(''); await loadGroups(); setSelectedGroupId(result.group.id); showToast?.('You joined the study group'); }
    catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  async function postUpdate(e) {
    e.preventDefault(); if (!selectedGroupId) return; setBusy(true); setError('');
    try { await api(`/api/groups/${selectedGroupId}/posts`, { method: 'POST', body: { body: message, resource_id: shareResourceId || null } }); setMessage(''); setShareResourceId(''); await loadDetail(selectedGroupId); }
    catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  async function leaveOrDelete() {
    if (!detail) return;
    const owner = detail.group.role === 'owner';
    if (!window.confirm(owner ? 'Delete this study group and its shared updates for everyone?' : 'Leave this study group?')) return;
    try { await api(owner ? `/api/groups/${selectedGroupId}` : `/api/groups/${selectedGroupId}/members/me`, { method: 'DELETE' }); setSelectedGroupId(null); setDetail(null); await loadGroups(); showToast?.(owner ? 'Study group deleted' : 'You left the study group'); }
    catch (err) { setError(err.message); }
  }
  async function removePost(postId) {
    if (!selectedGroupId || !window.confirm('Remove this group update?')) return;
    try { await api(`/api/groups/${selectedGroupId}/posts/${postId}`, { method: 'DELETE' }); await loadDetail(selectedGroupId); }
    catch (err) { setError(err.message); }
  }
  async function copyInvite() {
    try { await navigator.clipboard.writeText(detail.group.invite_code); showToast?.('Invite code copied'); }
    catch { setError('Clipboard access was blocked. Select and copy the invite code manually.'); }
  }
  return <div className="groups-page">
    <div className="groups-intro panel"><div><span className="eyebrow">LEARN BETTER, TOGETHER</span><h2>Study Groups</h2><p>Create a small study circle, invite classmates with a code, share notes, and keep the conversation around your learning in one place.</p></div><div className="groups-intro-icon"><Users size={28} /></div></div>
    <div className="groups-layout">
      <aside className="groups-sidebar">
        <section className="panel groups-action-card"><SectionTitle eyebrow="START A STUDY CIRCLE" title="Create a group" /><form className="groups-form" onSubmit={createGroup}><label>Group name<input required maxLength={120} value={groupName} onChange={(e) => setGroupName(e.target.value)} placeholder="e.g. Biology Revision Circle" /></label><label>Description (optional)<textarea rows={2} maxLength={500} value={groupDescription} onChange={(e) => setGroupDescription(e.target.value)} placeholder="What will your group study?" /></label><button className="button button-dark" disabled={busy}><Users size={15} />Create group</button></form></section>
        <section className="panel groups-action-card"><SectionTitle eyebrow="HAVE AN INVITE?" title="Join a group" /><form className="groups-form" onSubmit={joinGroup}><label>Invite code<input required maxLength={24} value={inviteCode} onChange={(e) => setInviteCode(e.target.value.toUpperCase())} placeholder="Enter group code" /></label><button className="button button-quiet" disabled={busy}><UserPlus size={15} />Join group</button></form></section>
        <section className="panel groups-list-card"><SectionTitle eyebrow="YOUR COMMUNITIES" title={`${groups.length} groups`} action="Refresh" onAction={loadGroups} />{groups.length ? <div className="groups-list">{groups.map((group) => <button className={`group-list-item ${selectedGroupId === group.id ? 'active' : ''}`} key={group.id} onClick={() => setSelectedGroupId(group.id)}><span className="group-avatar"><Users size={15} /></span><span className="group-list-copy"><strong>{group.name}</strong><small>{group.member_count} members · {group.role}</small></span></button>)}</div> : <EmptyState icon={Users} title="No groups yet" text="Create a group or join one with an invite code." />}</section>
      </aside>
      <section className="panel group-detail-panel">
        {detail ? <>
          <div className="group-detail-head"><div><span className="eyebrow">YOUR STUDY CIRCLE · {detail.group.member_count} MEMBERS</span><h2>{detail.group.name}</h2><p>{detail.group.description || 'A shared space for focused study and resource exchange.'}</p></div><div className="group-head-actions"><button className="button button-quiet" onClick={copyInvite}><Copy size={14} />Copy invite code</button><button className="icon-button subtle" onClick={leaveOrDelete} title={detail.group.role === 'owner' ? 'Delete group' : 'Leave group'}><Trash2 size={15} /></button></div></div>
          <div className="invite-code-row"><span>INVITE CODE</span><strong>{detail.group.invite_code}</strong><small>Share this code only with classmates you want to invite.</small></div>
          <div className="group-members"><span className="eyebrow">MEMBERS</span>{detail.members.map((member) => <span className="member-chip" key={member.user_id}><span>{member.username.slice(0, 1).toUpperCase()}</span>{member.username}{member.role === 'owner' ? ' · Owner' : ''}</span>)}</div>
          <div className="group-posts-head"><SectionTitle eyebrow="GROUP SPACE" title="Updates & shared resources" /></div>
          <form className="group-post-form" onSubmit={postUpdate}><label>Share an update<textarea rows={3} maxLength={3000} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Share a question, useful summary, or study update…" /></label><div className="form-two"><label>Attach a Resource Bank item (optional)<select value={shareResourceId} onChange={(e) => setShareResourceId(e.target.value)}><option value="">Don't share a file</option>{resources.map((resource) => <option key={resource.id} value={resource.id}>{resource.title}</option>)}</select></label><button className="button button-dark group-post-submit" disabled={busy || (!message.trim() && !shareResourceId)}><Send size={14} />Share with group</button></div></form>
          {detail.posts.length ? <div className="group-post-list">{detail.posts.map((post) => <article className="group-post" key={post.id}><div className="group-post-top"><div className="member-avatar">{post.username.slice(0, 1).toUpperCase()}</div><div><strong>{post.username}</strong><small>{new Date(post.created_at).toLocaleString()}</small></div>{(post.is_author || post.is_owner) && <button className="icon-button subtle" onClick={() => removePost(post.id)} title="Remove update"><Trash2 size={14} /></button>}</div>{post.body && <p>{post.body}</p>}{post.resource && <a className="shared-resource-link" href={post.resource.download_url || post.resource.url} target={post.resource.url ? '_blank' : undefined} rel={post.resource.url ? 'noreferrer' : undefined}><FileDown size={16} /><span><strong>{post.resource.title}</strong><small>{post.resource.resource_type.toUpperCase()} · Shared from Resource Bank</small></span>{post.resource.url ? <ExternalLink size={14} /> : <Download size={14} />}</a>}</article>)}</div> : <EmptyState icon={MessageCircle} title="Start the conversation" text="Share your first update or a study resource with this group." />}
        </> : <EmptyState icon={Users} title="Your study groups" text="Create a new group or join one with an invite code to start collaborating." />}
        {error && <div className="form-error groups-error">{error}</div>}
      </section>
    </div>
  </div>;
}

function SettingsPanel({ user, preferences, onSaveProfile, onSavePreferences }) {
  const [profile, setProfile] = useState({ username: user.username || '', email: user.email || '' });
  const [settings, setSettings] = useState({
    pomodoro_minutes: preferences.pomodoro_minutes ?? 25,
    short_break_minutes: preferences.short_break_minutes ?? 5,
    long_break_minutes: preferences.long_break_minutes ?? 15,
    daily_goal_hours: preferences.daily_goal_hours ?? 3.5,
    peak_focus_hours: preferences.peak_focus_hours || '09:00-12:00',
    theme: preferences.theme || 'cream',
    notifications_enabled: preferences.notifications_enabled ?? true,
  });
  const [profileError, setProfileError] = useState('');
  const [settingsError, setSettingsError] = useState('');
  const [profileSaving, setProfileSaving] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);

  useEffect(() => setProfile({ username: user.username || '', email: user.email || '' }), [user.username, user.email]);
  useEffect(() => setSettings({
    pomodoro_minutes: preferences.pomodoro_minutes ?? 25,
    short_break_minutes: preferences.short_break_minutes ?? 5,
    long_break_minutes: preferences.long_break_minutes ?? 15,
    daily_goal_hours: preferences.daily_goal_hours ?? 3.5,
    peak_focus_hours: preferences.peak_focus_hours || '09:00-12:00',
    theme: preferences.theme || 'cream',
    notifications_enabled: preferences.notifications_enabled ?? true,
  }), [preferences]);

  async function saveProfile(e) {
    e.preventDefault(); setProfileError(''); setProfileSaving(true);
    try { await onSaveProfile(profile); }
    catch (err) { setProfileError(err.message); }
    finally { setProfileSaving(false); }
  }
  async function saveSettings(e) {
    e.preventDefault(); setSettingsError(''); setSettingsSaving(true);
    try { await onSavePreferences({ ...settings, pomodoro_minutes: Number(settings.pomodoro_minutes), short_break_minutes: Number(settings.short_break_minutes), long_break_minutes: Number(settings.long_break_minutes), daily_goal_hours: Number(settings.daily_goal_hours) }); }
    catch (err) { setSettingsError(err.message); }
    finally { setSettingsSaving(false); }
  }

  return <div className="settings-page">
    <section className="panel settings-intro"><div className="settings-intro-mark"><Settings size={20} /></div><div><span className="eyebrow">MAKE AURA YOURS</span><h2>Settings & preferences</h2><p>Shape your focus rhythm, update your student profile, and choose how your workspace feels.</p></div></section>
    <div className="settings-grid">
      <section className="panel settings-panel"><SectionTitle eyebrow="YOUR ACCOUNT" title="Student profile" /><form className="settings-form" onSubmit={saveProfile}>
        <label>Username<input required minLength={3} maxLength={80} value={profile.username} onChange={(e) => setProfile({ ...profile, username: e.target.value })} /></label>
        <label>Email address<input required type="email" maxLength={255} value={profile.email} onChange={(e) => setProfile({ ...profile, email: e.target.value })} /></label>
        {profileError && <div className="form-error">{profileError}</div>}
        <button className="button button-dark" disabled={profileSaving}>{profileSaving ? 'Saving…' : 'Save profile'}</button>
      </form></section>
      <section className="panel settings-panel"><SectionTitle eyebrow="YOUR FOCUS RHYTHM" title="Pomodoro preferences" /><form className="settings-form" onSubmit={saveSettings}>
        <div className="form-two"><label>Focus length (minutes)<input type="number" min="10" max="90" step="1" required value={settings.pomodoro_minutes} onChange={(e) => setSettings({ ...settings, pomodoro_minutes: e.target.value })} /></label><label>Short break (minutes)<input type="number" min="1" max="30" step="1" required value={settings.short_break_minutes} onChange={(e) => setSettings({ ...settings, short_break_minutes: e.target.value })} /></label></div>
        <div className="form-two"><label>Long break (minutes)<input type="number" min="5" max="60" step="1" required value={settings.long_break_minutes} onChange={(e) => setSettings({ ...settings, long_break_minutes: e.target.value })} /></label><label>Daily study goal (hours)<input type="number" min="0.5" max="16" step="0.5" required value={settings.daily_goal_hours} onChange={(e) => setSettings({ ...settings, daily_goal_hours: e.target.value })} /></label></div>
        <label>Preferred focus window <input type="text" required pattern="([01][0-9]|2[0-3]):[0-5][0-9]-([01][0-9]|2[0-3]):[0-5][0-9]" value={settings.peak_focus_hours} onChange={(e) => setSettings({ ...settings, peak_focus_hours: e.target.value })} placeholder="09:00-12:00" /><small className="field-hint">Use 24-hour time, for example 09:00-12:00.</small></label>
        <label>Workspace appearance<select value={settings.theme} onChange={(e) => setSettings({ ...settings, theme: e.target.value })}><option value="cream">AURA cream</option><option value="night">Midnight forest</option></select></label>
        <label className="setting-toggle"><input type="checkbox" checked={Boolean(settings.notifications_enabled)} onChange={(e) => setSettings({ ...settings, notifications_enabled: e.target.checked })} /><span><strong>Study reminders enabled</strong><small>Save your reminder preference for the upcoming reminder feature.</small></span></label>
        {settingsError && <div className="form-error">{settingsError}</div>}
        <button className="button button-dark" disabled={settingsSaving}>{settingsSaving ? 'Saving…' : 'Save preferences'}</button>
      </form></section>
    </div>
  </div>;
}

function LearningHub({ subjects, onDataChanged, showToast }) {
  const [tab, setTab] = useState('plan');
  const [planDate, setPlanDate] = useState(localDate());
  const [plan, setPlan] = useState(null);
  const [planBusy, setPlanBusy] = useState(false);
  const [topic, setTopic] = useState('');
  const [subjectId, setSubjectId] = useState('');
  const [notes, setNotes] = useState('');
  const [difficulty, setDifficulty] = useState('standard');
  const [questionCount, setQuestionCount] = useState(5);
  const [quizBusy, setQuizBusy] = useState(false);
  const [quiz, setQuiz] = useState(null);
  const [quizAnswers, setQuizAnswers] = useState([]);
  const [quizResult, setQuizResult] = useState(null);
  const [quizHistory, setQuizHistory] = useState([]);
  const [flashcards, setFlashcards] = useState([]);
  const [cardIndex, setCardIndex] = useState(0);
  const [cardFlipped, setCardFlipped] = useState(false);
  const [cardFront, setCardFront] = useState('');
  const [cardBack, setCardBack] = useState('');
  const [flashBusy, setFlashBusy] = useState(false);
  const [revisionItems, setRevisionItems] = useState([]);
  const [revisionForm, setRevisionForm] = useState({ title: '', notes: '', due_date: localDate(), subject_id: '' });
  const [overview, setOverview] = useState({ due_flashcards: 0, total_flashcards: 0, due_revisions: 0, open_revisions: 0, recent_attempts: [] });
  const [error, setError] = useState('');

  const loadPlan = async (dateValue = planDate) => {
    setPlanBusy(true); setError('');
    try { setPlan(await api(`/api/learning/daily-plan?date=${encodeURIComponent(dateValue)}`)); }
    catch (err) { setError(err.message); }
    finally { setPlanBusy(false); }
  };
  const loadLearningData = async () => {
    try {
      const [summary, cards, revisions, quizzes] = await Promise.all([
        api('/api/learning/overview'), api('/api/learning/flashcards?due_only=true'), api('/api/learning/revisions'), api('/api/learning/quizzes'),
      ]);
      setOverview(summary); setFlashcards(cards); setRevisionItems(revisions); setQuizHistory(quizzes);
      if (cardIndex >= cards.length) setCardIndex(0);
    } catch (err) { setError(err.message); }
  };
  useEffect(() => { loadPlan(localDate()); loadLearningData(); }, []);

  async function applyPlan() {
    setPlanBusy(true); setError('');
    try {
      const result = await api('/api/learning/daily-plan/apply', { method: 'POST', body: { date: planDate } });
      showToast(result.message); await loadPlan(planDate); await onDataChanged();
    } catch (err) { setError(err.message); showToast(err.message, 'error'); }
    finally { setPlanBusy(false); }
  }
  async function createQuiz(e) {
    e.preventDefault(); setQuizBusy(true); setError(''); setQuizResult(null); setQuiz(null);
    try {
      const result = await api('/api/learning/quizzes/generate', { method: 'POST', body: {
        topic, subject_id: subjectId || null, notes, difficulty, count: Number(questionCount),
      } });
      setQuiz(result.quiz); setQuizAnswers(Array(result.quiz.questions.length).fill(-1));
      showToast('Your quiz is ready. Answer without looking at your notes.'); await loadLearningData();
    } catch (err) { setError(err.message); }
    finally { setQuizBusy(false); }
  }
  async function submitQuiz() {
    if (!quiz || quizAnswers.some((answer) => answer < 0)) { setError('Choose an answer for every question before submitting.'); return; }
    setQuizBusy(true); setError('');
    try {
      const result = await api(`/api/learning/quizzes/${quiz.id}/attempts`, { method: 'POST', body: { answers: quizAnswers } });
      setQuizResult(result); showToast(`Quiz completed: ${result.score}/${result.total}`); await loadLearningData();
    } catch (err) { setError(err.message); }
    finally { setQuizBusy(false); }
  }
  async function loadSavedQuiz(id) {
    setError(''); setQuizResult(null);
    try { const result = await api(`/api/learning/quizzes/${id}`); setQuiz(result.quiz); setQuizAnswers(Array(result.quiz.questions.length).fill(-1)); setTab('quiz'); }
    catch (err) { setError(err.message); }
  }
  async function generateCards(e) {
    e.preventDefault(); setFlashBusy(true); setError('');
    try {
      const result = await api('/api/learning/flashcards/generate', { method: 'POST', body: {
        topic: topic || 'General study', subject_id: subjectId || null, notes, count: 12,
      } });
      setFlashcards((old) => [...result.flashcards, ...old]); setCardIndex(0); setCardFlipped(false);
      showToast(result.message); await loadLearningData();
    } catch (err) { setError(err.message); }
    finally { setFlashBusy(false); }
  }
  async function createManualCard(e) {
    e.preventDefault(); setFlashBusy(true); setError('');
    try {
      const result = await api('/api/learning/flashcards', { method: 'POST', body: {
        front: cardFront, back: cardBack, subject_id: subjectId || null,
      } });
      setFlashcards((old) => [result.flashcard, ...old]); setCardFront(''); setCardBack('');
      showToast('Flashcard created'); await loadLearningData();
    } catch (err) { setError(err.message); }
    finally { setFlashBusy(false); }
  }
  async function rateCard(rating) {
    const card = flashcards[cardIndex]; if (!card) return;
    setFlashBusy(true); setError('');
    try {
      const result = await api(`/api/learning/flashcards/${card.id}/review`, { method: 'PATCH', body: { rating } });
      const next = [...flashcards]; next.splice(cardIndex, 1); setFlashcards(next); setCardIndex(0); setCardFlipped(false);
      showToast(result.message); await loadLearningData();
    } catch (err) { setError(err.message); }
    finally { setFlashBusy(false); }
  }
  async function addRevision(e) {
    e.preventDefault(); setError('');
    try {
      await api('/api/learning/revisions', { method: 'POST', body: { ...revisionForm, subject_id: revisionForm.subject_id || null } });
      setRevisionForm({ title: '', notes: '', due_date: localDate(), subject_id: '' }); showToast('Revision reminder added'); await loadLearningData();
    } catch (err) { setError(err.message); }
  }
  async function updateRevision(id, body) {
    try { await api(`/api/learning/revisions/${id}`, { method: 'PATCH', body }); await loadLearningData(); }
    catch (err) { setError(err.message); }
  }
  async function deleteRevision(id) {
    if (!window.confirm('Delete this revision reminder?')) return;
    try { await api(`/api/learning/revisions/${id}`, { method: 'DELETE' }); await loadLearningData(); showToast('Revision reminder deleted'); }
    catch (err) { setError(err.message); }
  }

  const activeCard = flashcards[cardIndex];
  const tabs = [
    ['plan', 'Daily plan', CalendarCheck], ['quiz', 'Active recall', BrainCircuit],
    ['cards', 'Flashcards', Layers], ['revisions', 'Revision queue', RotateCcw],
  ];
  return <div className="learning-page">
    <section className="panel learning-hero">
      <div className="learning-hero-mark"><BrainCircuit size={24} /></div>
      <div className="learning-hero-copy"><span className="eyebrow">PHASE 2 · INTELLIGENT LEARNING</span><h2>Learn actively. Remember longer.</h2><p>Plan focused work, test what you know, and revisit difficult ideas at the right time.</p></div>
      <div className="learning-stats"><div><strong>{overview.due_flashcards || 0}</strong><span>cards due</span></div><div><strong>{overview.due_revisions || 0}</strong><span>revisions due</span></div></div>
    </section>
    <div className="learning-tabs">{tabs.map(([id, label, Icon]) => <button key={id} className={tab === id ? 'active' : ''} onClick={() => { setTab(id); setError(''); if (id === 'plan') loadPlan(); }}>{<Icon size={15} />}{label}</button>)}</div>
    {error && <div className="learning-error"><CircleHelp size={15} />{error}<button onClick={() => setError('')} aria-label="Dismiss"><X size={14} /></button></div>}

    {tab === 'plan' && <div className="learning-grid">
      <section className="panel learning-main-panel">
        <div className="learning-panel-head"><div><span className="eyebrow">ADAPTIVE STUDY SCHEDULER</span><h2>Your study plan</h2><p>Built around your course urgency, remaining study targets, history, and saved calendar blocks.</p></div><button className="icon-button" onClick={() => loadPlan()} title="Refresh plan"><RefreshCw size={16} /></button></div>
        <div className="learning-toolbar"><label>Planning date<input type="date" value={planDate} onChange={(e) => { setPlanDate(e.target.value); loadPlan(e.target.value); }} /></label><span className="learning-engine-label"><Sparkles size={13} />Rules-based adaptive planner</span></div>
        {planBusy && <div className="learning-empty">Building a schedule that fits your available time…</div>}
        {!planBusy && plan && <>
          <div className="plan-summary"><div><strong>{Math.floor(plan.planned_minutes / 60)}h {plan.planned_minutes % 60}m</strong><span>planned focus time</span></div><div><strong>{plan.items.length}</strong><span>study blocks</span></div><div><strong>{Math.round(plan.goal_minutes / 60 * 10) / 10}h</strong><span>daily target</span></div></div>
          <p className="panel-description">{plan.message}</p>
          <div className="planned-blocks">{plan.items.map((item, index) => <div className="planned-block" key={`${item.subject_id}-${item.start_time}`}><div className="planned-block-time">{new Date(item.start_time).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}<span>{item.duration_minutes} min</span></div><div className="planned-block-content"><span className="planned-block-index">BLOCK {index + 1} · PRIORITY {item.priority_score}</span><strong>{item.title}</strong><p>{item.reason}</p></div></div>)}</div>
          <button className="button button-dark" disabled={planBusy || !plan.items.length} onClick={applyPlan}><CalendarCheck size={15} />Add full plan to schedule</button>
          <small className="field-hint">AURA re-checks availability before saving, so existing events are not overwritten.</small>
        </>}
      </section>
      <aside className="panel learning-side-panel"><div className="learning-side-icon"><Target size={22} /></div><span className="eyebrow">HOW THE PLAN IS BUILT</span><h3>Priority with breathing room.</h3><ul><li>Courses closer to exams receive more weight.</li><li>Difficulty and unfinished target hours influence priority.</li><li>Your preferred focus window and existing events define available time.</li><li>Blocks include short buffers rather than back-to-back study all day.</li></ul><div className="learning-side-note">The plan is a suggestion. Review it before adding anything to your calendar.</div></aside>
    </div>}

    {tab === 'quiz' && <div className="learning-grid">
      <section className="panel learning-main-panel"><div className="learning-panel-head"><div><span className="eyebrow">ACTIVE RECALL QUIZZER</span><h2>Test your understanding</h2><p>Generate questions from your own notes, then answer without looking at them.</p></div><BrainCircuit size={23} className="learning-heading-icon" /></div>
        {!quiz && !quizResult && <form className="learning-form" onSubmit={createQuiz}><div className="form-two"><label>Topic<input required value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="e.g. Database normalization" /></label><label>Course (optional)<select value={subjectId} onChange={(e) => setSubjectId(e.target.value)}><option value="">No linked course</option>{subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}</select></label></div><div className="form-three"><label>Difficulty<select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}><option value="easy">Easy</option><option value="standard">Standard</option><option value="hard">Hard</option></select></label><label>Questions<select value={questionCount} onChange={(e) => setQuestionCount(Number(e.target.value))}><option value={3}>3 questions</option><option value={5}>5 questions</option><option value={8}>8 questions</option><option value={10}>10 questions</option></select></label></div><label>Paste study notes<textarea rows={7} value={notes} onChange={(e) => setNotes(e.target.value)} required minLength={20} maxLength={12000} placeholder={'Paste your lecture notes, textbook summary, or topic notes here…\n\nWithout a Gemini API key, use one Term: definition pair per line.'} /><small className="field-hint">With Gemini enabled, normal notes work. Offline mode requires at least two Term: definition lines.</small></label><button className="button button-dark" disabled={quizBusy}>{quizBusy ? <LoaderCircle size={15} className="spin" /> : <Sparkles size={15} />}Generate quiz</button></form>}
        {quiz && !quizResult && <div className="quiz-workspace"><div className="quiz-workspace-head"><div><span className="eyebrow">{quiz.difficulty.toUpperCase()} · {quiz.questions.length} QUESTIONS</span><h3>{quiz.title}</h3></div><button className="button button-quiet" onClick={() => { setQuiz(null); setQuizResult(null); }}>New quiz</button></div>{quiz.questions.map((question, index) => <div className="quiz-question" key={index}><span className="eyebrow">QUESTION {index + 1} OF {quiz.questions.length}</span><strong>{question.question}</strong><div className="quiz-options">{question.options.map((option, optionIndex) => <label key={optionIndex} className={quizAnswers[index] === optionIndex ? 'quiz-option selected' : 'quiz-option'}><input type="radio" name={`question-${index}`} checked={quizAnswers[index] === optionIndex} onChange={() => setQuizAnswers((old) => old.map((answer, i) => i === index ? optionIndex : answer))} /><span>{option}</span></label>)}</div></div>)}<button className="button button-dark" disabled={quizBusy} onClick={submitQuiz}>Submit answers <ArrowRight size={15} /></button></div>}
        {quizResult && <div className="quiz-results"><div className="quiz-score"><strong>{quizResult.percent}%</strong><span>{quizResult.score} correct out of {quizResult.total}</span></div><h3>{quizResult.percent >= 80 ? 'Strong understanding.' : quizResult.percent >= 60 ? 'Good progress. Keep reviewing.' : 'Let’s strengthen these topics.'}</h3>{quizResult.results.map((result, index) => <div className={`quiz-result-row ${result.is_correct ? 'correct' : 'incorrect'}`} key={index}><div><strong>{index + 1}. {result.question}</strong><p>{result.is_correct ? 'Correct' : 'Not quite'} · {result.explanation}</p></div>{result.is_correct ? <CheckCircle2 size={18} /> : <CircleHelp size={18} />}</div>)}{quizResult.revision_created && <div className="learning-side-note">AURA added a revision reminder for this course because your score was below 70%.</div>}<button className="button button-dark" onClick={() => { setQuiz(null); setQuizResult(null); setQuizAnswers([]); }}>Create another quiz</button></div>}
      </section>
      <aside className="panel learning-side-panel"><span className="eyebrow">RECENT QUIZZES</span><h3>Your practice history</h3>{quizHistory.length ? <div className="learning-history">{quizHistory.map((item) => <button key={item.id} onClick={() => loadSavedQuiz(item.id)}><span><strong>{item.title}</strong><small>{item.question_count} questions · {item.difficulty}</small></span><ArrowRight size={15} /></button>)}</div> : <p className="panel-description">Your completed quizzes will appear here.</p>}<div className="learning-side-note">Quizzes are stored privately in your account. Answers are not sent to the browser until you submit the quiz.</div></aside>
    </div>}

    {tab === 'cards' && <div className="learning-grid">
      <section className="panel learning-main-panel"><div className="learning-panel-head"><div><span className="eyebrow">SPACED REPETITION</span><h2>Flashcard practice</h2><p>Recall the answer, flip the card, then rate how well you knew it.</p></div><Layers size={23} className="learning-heading-icon" /></div>
        {activeCard ? <div className="flashcard-study"><div className="flashcard-count">CARD {cardIndex + 1} OF {flashcards.length} · DUE {activeCard.due_date}</div><button className={`flashcard-face ${cardFlipped ? 'flipped' : ''}`} onClick={() => setCardFlipped((old) => !old)}><span className="eyebrow">{cardFlipped ? 'ANSWER' : 'RECALL PROMPT'}</span><strong>{cardFlipped ? activeCard.back : activeCard.front}</strong><small>Click to {cardFlipped ? 'see prompt' : 'reveal answer'}</small></button>{cardFlipped && <div className="flashcard-ratings"><button disabled={flashBusy} onClick={() => rateCard('again')}>Again <small>1 day</small></button><button disabled={flashBusy} onClick={() => rateCard('hard')}>Hard <small>Short interval</small></button><button disabled={flashBusy} onClick={() => rateCard('good')}>Good <small>Normal interval</small></button><button disabled={flashBusy} onClick={() => rateCard('easy')}>Easy <small>Longer interval</small></button></div>}<div className="flashcard-controls"><button className="button button-quiet" onClick={() => { setCardIndex((old) => (old + flashcards.length - 1) % flashcards.length); setCardFlipped(false); }}><ChevronLeft size={15} />Previous</button><button className="button button-quiet" onClick={() => { setCardIndex((old) => (old + 1) % flashcards.length); setCardFlipped(false); }}>Next<ChevronRight size={15} /></button></div></div> : <div className="learning-empty"><Layers size={24} /><strong>No flashcards due right now</strong><span>Generate cards, add one manually, or return when your next review is due.</span></div>}
        <div className="learning-divider" /><form className="learning-form" onSubmit={generateCards}><span className="eyebrow">GENERATE FROM NOTES</span><div className="form-two"><label>Topic<input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="e.g. Cell biology" /></label><label>Course (optional)<select value={subjectId} onChange={(e) => setSubjectId(e.target.value)}><option value="">No linked course</option>{subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}</select></label></div><label>Study notes<textarea rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Paste notes to turn into flashcards…" /><small className="field-hint">Offline mode supports Term: definition lines; Gemini can turn regular notes into cards.</small></label><button className="button button-dark" disabled={flashBusy}><Sparkles size={15} />Generate flashcards</button></form>
        <div className="learning-divider" /><form className="learning-form" onSubmit={createManualCard}><span className="eyebrow">CREATE ONE YOURSELF</span><label>Front / question<input required value={cardFront} onChange={(e) => setCardFront(e.target.value)} placeholder="What is active transport?" /></label><label>Back / answer<textarea required rows={2} value={cardBack} onChange={(e) => setCardBack(e.target.value)} placeholder="Movement across a membrane using energy…" /></label><button className="button button-quiet" disabled={flashBusy}><Plus size={15} />Add flashcard</button></form>
      </section>
      <aside className="panel learning-side-panel"><span className="eyebrow">YOUR MEMORY DECK</span><h3>Small reviews add up.</h3><div className="plan-summary"><div><strong>{overview.due_flashcards || 0}</strong><span>due today</span></div><div><strong>{overview.total_flashcards || 0}</strong><span>total cards</span></div></div><p className="panel-description">Again brings a card back tomorrow. Good and Easy gradually increase the review interval as your recall improves.</p><div className="learning-history">{flashcards.slice(0, 8).map((card) => <div key={card.id}><span><strong>{card.front}</strong><small>Next review · {card.due_date}</small></span><button className="icon-button subtle" onClick={async () => { if (window.confirm('Delete this flashcard?')) { await api(`/api/learning/flashcards/${card.id}`, { method: 'DELETE' }); await loadLearningData(); showToast('Flashcard deleted'); } }}><Trash2 size={14} /></button></div>)}</div></aside>
    </div>}

    {tab === 'revisions' && <div className="learning-grid">
      <section className="panel learning-main-panel"><div className="learning-panel-head"><div><span className="eyebrow">REVISION TRACKER</span><h2>Return to what matters</h2><p>Keep difficult ideas visible and schedule a second look before exams.</p></div><RotateCcw size={23} className="learning-heading-icon" /></div>
        <form className="learning-form revision-create-form" onSubmit={addRevision}><label>Revision topic<input required value={revisionForm.title} onChange={(e) => setRevisionForm({ ...revisionForm, title: e.target.value })} placeholder="e.g. Revise normalization and keys" /></label><div className="form-two"><label>Course (optional)<select value={revisionForm.subject_id} onChange={(e) => setRevisionForm({ ...revisionForm, subject_id: e.target.value })}><option value="">No linked course</option>{subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}</select></label><label>Review date<input type="date" required value={revisionForm.due_date} onChange={(e) => setRevisionForm({ ...revisionForm, due_date: e.target.value })} /></label></div><label>Notes (optional)<textarea rows={2} value={revisionForm.notes} onChange={(e) => setRevisionForm({ ...revisionForm, notes: e.target.value })} placeholder="What should you revisit?" /></label><button className="button button-dark"><Plus size={15} />Schedule revision</button></form>
        <div className="learning-divider" /><div className="revision-list">{revisionItems.length ? revisionItems.map((item) => <div className={`revision-item ${item.status === 'done' ? 'completed' : ''}`} key={item.id}><button className="revision-check" onClick={() => updateRevision(item.id, { status: item.status === 'done' ? 'todo' : 'done' })}>{item.status === 'done' ? <CheckCircle2 size={17} /> : <span />}</button><div className="revision-item-copy"><strong>{item.title}</strong><span>{item.due_date} · {item.status === 'done' ? 'Completed' : (item.due_date < localDate() ? 'Overdue' : 'Upcoming')}</span>{item.notes && <p>{item.notes}</p>}</div><button className="icon-button subtle" onClick={() => deleteRevision(item.id)} title="Delete revision"><Trash2 size={14} /></button></div>) : <div className="learning-empty"><CalendarCheck size={23} /><strong>Your revision queue is clear.</strong><span>Low quiz scores and reminders you add will appear here.</span></div>}</div>
      </section>
      <aside className="panel learning-side-panel"><span className="eyebrow">AUTOMATIC REVISION</span><h3>Turn mistakes into a plan.</h3><p className="panel-description">When you score below 70% on a quiz linked to a course, AURA automatically creates a revision reminder for the next day. You can edit, complete, or delete any reminder.</p><div className="plan-summary"><div><strong>{overview.due_revisions || 0}</strong><span>due now</span></div><div><strong>{overview.open_revisions || 0}</strong><span>open items</span></div></div></aside>
    </div>}
  </div>;
}


function ProductivityHub({ showToast, onUnreadChange, onSaveGoal }) {
  const [days, setDays] = useState(7);
  const [overview, setOverview] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [reminders, setReminders] = useState([]);
  const [unread, setUnread] = useState(0);
  const [goalInput, setGoalInput] = useState('3.5');
  const [reminderForm, setReminderForm] = useState({ title: '', message: '', remind_at: toLocalDateTimeInput(new Date(Date.now() + 60 * 60 * 1000)) });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setBusy(true); setError('');
    try {
      const [analytics, notificationData, reminderData] = await Promise.all([
        api(`/api/productivity/overview?days=${days}`),
        api('/api/productivity/notifications?limit=40'),
        api('/api/productivity/reminders'),
      ]);
      setOverview(analytics);
      setNotifications(notificationData.items || []);
      setUnread(notificationData.unread || 0);
      onUnreadChange?.(notificationData.unread || 0);
      setReminders(reminderData || []);
      setGoalInput(String(analytics.stats?.daily_goal_hours ?? 3.5));
    } catch (err) { setError(err.message || 'Could not load productivity data.'); }
    finally { setBusy(false); }
  }, [days, onUnreadChange]);

  useEffect(() => { load(); }, [load]);

  const markRead = async (id) => {
    try { await api(`/api/productivity/notifications/${id}/read`, { method: 'PATCH' }); await load(); }
    catch (err) { showToast(err.message, 'error'); }
  };
  const readAll = async () => {
    try { await api('/api/productivity/notifications/read-all', { method: 'POST' }); await load(); showToast('All notifications marked as read'); }
    catch (err) { showToast(err.message, 'error'); }
  };
  const removeNotification = async (id) => {
    try { await api(`/api/productivity/notifications/${id}`, { method: 'DELETE' }); await load(); }
    catch (err) { showToast(err.message, 'error'); }
  };
  const saveGoal = async (event) => {
    event.preventDefault();
    const value = Number(goalInput);
    if (!Number.isFinite(value) || value < 0.5 || value > 16) { showToast('Daily goal must be between 0.5 and 16 hours.', 'error'); return; }
    try { await onSaveGoal(value); await load(); }
    catch (err) { showToast(err.message, 'error'); }
  };
  const createReminder = async (event) => {
    event.preventDefault();
    try {
      await api('/api/productivity/reminders', { method: 'POST', body: reminderForm });
      setReminderForm({ title: '', message: '', remind_at: toLocalDateTimeInput(new Date(Date.now() + 60 * 60 * 1000)) });
      showToast('Reminder scheduled'); await load();
    } catch (err) { showToast(err.message, 'error'); }
  };
  const dismissReminder = async (id) => {
    try { await api(`/api/productivity/reminders/${id}`, { method: 'DELETE' }); await load(); showToast('Reminder removed'); }
    catch (err) { showToast(err.message, 'error'); }
  };
  const stats = overview?.stats || {};
  const goalPercent = Math.min(100, Number(stats.goal_progress_percent || 0));
  const dueReminders = reminders.filter((item) => item.status === 'pending');
  const heatmap = overview?.heatmap || [];

  return <div className="productivity-page">
    <section className="productivity-hero panel">
      <div className="productivity-hero-copy"><span className="eyebrow">YOUR CONSISTENCY, MADE VISIBLE</span><h2>Progress you can build on.</h2><p>See your study rhythm, celebrate milestones, and keep important dates from slipping by.</p></div>
      <div className="productivity-period"><label htmlFor="productivity-period">REPORT PERIOD</label><select id="productivity-period" value={days} onChange={(e) => setDays(Number(e.target.value))}><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option></select><button className="button button-quiet" onClick={load}><RefreshCw size={14} />Refresh</button></div>
    </section>
    {error && <div className="learning-error"><CircleHelp size={15} />{error}<button onClick={() => setError('')}><X size={14} /></button></div>}
    <section className="productivity-metrics">
      <article className="productivity-metric"><span><Clock3 size={15} />STUDY HOURS</span><strong>{Number(stats.period_hours || 0).toFixed(1)}<small>hrs</small></strong><p>Across {days} days</p></article>
      <article className="productivity-metric"><span><Zap size={15} />FOCUS SESSIONS</span><strong>{stats.period_sessions || 0}</strong><p>Completed Pomodoro sessions</p></article>
      <article className="productivity-metric"><span><Flame size={15} />CURRENT STREAK</span><strong>{stats.current_streak || 0}<small>days</small></strong><p>Longest: {stats.longest_streak || 0} days</p></article>
      <article className="productivity-metric"><span><TrendingUp size={15} />DAILY AVERAGE</span><strong>{Number(stats.average_daily_hours || 0).toFixed(1)}<small>hrs</small></strong><p>{stats.goal_consistency_percent || 0}% goal consistency</p></article>
    </section>

    <section className="panel productivity-goal-panel">
      <div className="productivity-goal-head"><div><span className="eyebrow">TODAY'S STUDY GOAL</span><h3>{Number(stats.today_hours || 0).toFixed(1)} of {Number(stats.daily_goal_hours || 3.5).toFixed(1)} hours</h3><p>{goalPercent >= 100 ? 'Daily goal reached. Remember to leave room for rest.' : `${Math.max(0, Number(stats.daily_goal_hours || 3.5) - Number(stats.today_hours || 0)).toFixed(1)} hours left to reach today's target.`}</p></div><div className="goal-percent">{goalPercent}%</div></div>
      <div className="productivity-goal-track"><div style={{ width: `${goalPercent}%` }} /></div>
      <form className="goal-edit-form" onSubmit={saveGoal}><label>Update daily target (hours)<input type="number" min="0.5" max="16" step="0.5" value={goalInput} onChange={(e) => setGoalInput(e.target.value)} /></label><button className="button button-dark" type="submit">Save goal</button></form>
    </section>

    <div className="productivity-content-grid">
      <section className="panel productivity-chart-panel"><SectionTitle eyebrow="STUDY TREND" title={`${days}-day activity`} /><div className="productivity-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={overview?.daily || []} margin={{ top: 10, right: 8, bottom: 4, left: -18 }}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#ece9df" /><XAxis dataKey="label" tick={{ fontSize: 10, fill: '#92968a' }} interval={days === 90 ? 8 : days === 30 ? 3 : 0} /><YAxis tick={{ fontSize: 9, fill: '#92968a' }} /><Tooltip formatter={(value) => [`${Number(value).toFixed(2)} hours`, 'Study time']} /><Bar dataKey="hours" fill="#8EA98F" radius={[5, 5, 0, 0]} maxBarSize={days === 90 ? 12 : 28} /></BarChart></ResponsiveContainer></div><p className="productivity-chart-note">Hours are calculated from manual study logs and focus sessions. Course-linked timer sessions are not counted twice.</p></section>

      <section className="panel productivity-peak-panel"><SectionTitle eyebrow="FOCUS PATTERN" title="When you tend to focus" /><div className="productivity-chart peak-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={overview?.hourly_focus || []} margin={{ top: 7, right: 4, bottom: 4, left: -22 }}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#ece9df" /><XAxis dataKey="hour" tick={{ fontSize: 8, fill: '#92968a' }} interval={2} /><YAxis allowDecimals={false} tick={{ fontSize: 9, fill: '#92968a' }} /><Tooltip formatter={(value) => [value, 'Focus sessions']} /><Bar dataKey="sessions" fill="#AF91DE" radius={[4, 4, 0, 0]} maxBarSize={17} /></BarChart></ResponsiveContainer></div><p className="productivity-chart-note">{stats.peak_focus_hour ? `Most recorded session starts: ${stats.peak_focus_hour}.` : 'Complete a few focus sessions to reveal your strongest start time.'}</p></section>

      <section className="panel productivity-heatmap-panel"><SectionTitle eyebrow="70-DAY CONSISTENCY" title="Your study activity" /><div className="heatmap-grid" role="img" aria-label="Study activity heatmap for the past 70 days">{heatmap.map((day) => <span key={day.date} className={`heatmap-cell heat-${day.level}`} title={`${day.date}: ${day.hours} study hours, ${day.sessions} sessions`} />)}</div><div className="heatmap-legend"><span>Less</span>{[0, 1, 2, 3, 4].map((level) => <i key={level} className={`heatmap-cell heat-${level}`} />)}<span>More</span><small>{heatmap[0]?.date} – {heatmap[heatmap.length - 1]?.date}</small></div></section>

      <section className="panel productivity-subject-panel"><SectionTitle eyebrow="WHERE YOUR TIME GOES" title="Course study hours" />{overview?.subjects?.length ? <div className="productivity-subject-list">{overview.subjects.map((subject, index) => { const total = overview.subjects.reduce((sum, item) => sum + Number(item.hours || 0), 0) || 1; const colors = ['#7f9f81', '#a98bd8', '#d6a17f', '#7da9b4', '#b5a66d', '#a77d8c']; return <div className="productivity-subject-row" key={subject.name}><div><strong>{subject.name}</strong><span>{subject.hours.toFixed(1)} hrs</span></div><div className="productivity-subject-track"><i style={{ width: `${subject.hours / total * 100}%`, background: colors[index % colors.length] }} /></div></div>; })}</div> : <EmptyState icon={BookOpen} title="No course study logs yet" text="Log study time against a course to see how your effort is distributed." />}</section>

      <section className="panel productivity-insights-panel"><SectionTitle eyebrow="AURA OBSERVATIONS" title="Small, useful insights" />{(overview?.insights || []).map((insight, index) => <div className="productivity-insight" key={index}><span><Sparkles size={14} /></span><p>{insight}</p></div>)}</section>

      <section className="panel productivity-achievements-panel"><SectionTitle eyebrow="MILESTONES" title="Achievements" /><div className="achievement-grid">{(overview?.achievements || []).map((item) => <article className={`achievement-card ${item.unlocked ? 'unlocked' : ''}`} key={item.key}><div className="achievement-icon">{item.icon === 'flame' ? <Flame size={17} /> : item.icon === 'trophy' ? <Trophy size={17} /> : item.icon === 'brain' ? <BrainCircuit size={17} /> : item.icon === 'clock' ? <Clock3 size={17} /> : item.icon === 'graduation-cap' ? <GraduationCap size={17} /> : item.icon === 'target' ? <Target size={17} /> : item.icon === 'zap' ? <Zap size={17} /> : <Award size={17} />}</div><strong>{item.title}</strong><p>{item.description}</p>{item.unlocked ? <small>Unlocked {item.earned_at ? new Date(item.earned_at).toLocaleDateString() : ''}</small> : <div className="achievement-progress"><i style={{ width: `${item.progress}%` }} /></div>}</article>)}</div></section>

      <section className="panel productivity-notifications-panel"><div className="productivity-section-head"><SectionTitle eyebrow="YOUR INBOX" title={`Notifications${unread ? ` · ${unread} unread` : ''}`} /><button className="text-action" disabled={!unread} onClick={readAll}>Mark all read <Check size={13} /></button></div>{notifications.length ? <div className="productivity-notification-list">{notifications.map((item) => <article className={`productivity-notification ${item.is_read ? 'read' : 'unread'}`} key={item.id}><div className={`notification-kind ${item.kind}`}>{item.kind === 'exam' ? <CalendarDays size={15} /> : item.kind === 'task' ? <CheckCircle2 size={15} /> : item.kind === 'achievement' ? <Trophy size={15} /> : item.kind === 'goal' ? <Target size={15} /> : <Bell size={15} />}</div><div className="notification-copy"><strong>{item.title}</strong><p>{item.message}</p><small>{item.created_at ? new Date(item.created_at).toLocaleString() : ''}</small></div><div className="notification-actions">{!item.is_read && <button className="icon-button subtle" title="Mark as read" onClick={() => markRead(item.id)}><Check size={14} /></button>}<button className="icon-button subtle" title="Delete notification" onClick={() => removeNotification(item.id)}><Trash2 size={14} /></button></div></article>)}</div> : <EmptyState icon={Bell} title="You're all caught up" text="Exam and task reminders will appear here when deadlines get close." />}</section>

      <section className="panel productivity-reminders-panel"><SectionTitle eyebrow="PLAN AHEAD" title="Personal reminders" /><form className="productivity-reminder-form" onSubmit={createReminder}><label>Reminder title<input required maxLength={180} value={reminderForm.title} onChange={(e) => setReminderForm({ ...reminderForm, title: e.target.value })} placeholder="e.g. Review lecture notes" /></label><label>Message (optional)<input maxLength={600} value={reminderForm.message} onChange={(e) => setReminderForm({ ...reminderForm, message: e.target.value })} placeholder="What should you remember?" /></label><label>Remind me at<input required type="datetime-local" value={reminderForm.remind_at} onChange={(e) => setReminderForm({ ...reminderForm, remind_at: e.target.value })} /></label><button className="button button-dark" type="submit"><Plus size={14} />Add reminder</button></form><div className="reminder-list">{reminders.length ? reminders.map((item) => <article className={`reminder-item ${item.status}`} key={item.id}><span className="reminder-clock"><CalendarClock size={15} /></span><div><strong>{item.title}</strong><p>{item.message || 'Personal reminder'}</p><small>{new Date(item.remind_at).toLocaleString()} · {item.status === 'delivered' ? 'Notified' : 'Upcoming'}</small></div><button className="icon-button subtle" title="Remove reminder" onClick={() => dismissReminder(item.id)}><Trash2 size={14} /></button></article>) : <p className="productivity-chart-note">No personal reminders scheduled yet.</p>}</div><p className="reminder-disclaimer">Reminders are delivered inside AURA while the application is open. Keep the app running to receive due reminder alerts.</p></section>
    </div>
    {busy && <div className="productivity-loading"><LoaderCircle size={14} />Refreshing your productivity data…</div>}
  </div>;
}

function toLocalDateTimeInput(value) {
  const d = value instanceof Date ? value : new Date(value);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}T${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function App() {
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [page, setPage] = useState('dashboard');
  const [scheduleDate, setScheduleDate] = useState(localDate());
  const [dashboard, setDashboard] = useState({ subjects: [], projects: [], schedule: [], stats: {}, preferences: {} });
  const [recommendations, setRecommendations] = useState(null);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState(null);
  const [unreadNotifications, setUnreadNotifications] = useState(0);
  const showToast = useCallback((message, type = 'success') => setToast({ message, type }), []);

  useEffect(() => {
    api('/api/me').then((data) => { setCsrfToken(data.csrf_token); setUser(data.user); }).catch(() => setUser(null)).finally(() => setAuthLoading(false));
  }, []);

  const refreshDashboard = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      const dateQuery = encodeURIComponent(scheduleDate);
      const [data, ai] = await Promise.all([api(`/api/dashboard?date=${dateQuery}`), api(`/api/ai/recommendations?date=${dateQuery}`)]);
      setDashboard(data); setRecommendations(ai);
      useTimerStore.getState().setDurations(data.preferences.pomodoro_minutes || 25, data.preferences.short_break_minutes || 5, data.preferences.long_break_minutes || 15);
    } catch (err) { if (err.status === 401) setUser(null); else showToast(err.message, 'error'); }
    finally { setLoading(false); }
  }, [user, scheduleDate, showToast]);
  useEffect(() => { if (user) refreshDashboard(); }, [user, refreshDashboard]);
  useEffect(() => {
    document.documentElement.dataset.theme = dashboard.preferences?.theme || 'cream';
    return () => { delete document.documentElement.dataset.theme; };
  }, [dashboard.preferences?.theme]);
  useEffect(() => {
    if (!user) { setUnreadNotifications(0); return undefined; }
    let active = true;
    const checkProductivity = async () => {
      try {
        const [notificationData, dueData] = await Promise.all([
          api('/api/productivity/notifications?limit=1'),
          api('/api/productivity/reminders/due'),
        ]);
        if (!active) return;
        setUnreadNotifications(notificationData.unread || 0);
        if ((dueData.due || []).length && dueData.notifications_enabled !== false) {
          const count = dueData.due.length;
          showToast(count === 1 ? `Reminder due: ${dueData.due[0].title}` : `${count} reminders are due. Open Productivity to review them.`);
        }
      } catch { /* The dashboard remains usable if reminder polling is temporarily unavailable. */ }
    };
    checkProductivity();
    const interval = window.setInterval(checkProductivity, 60000);
    return () => { active = false; window.clearInterval(interval); };
  }, [user, showToast]);

  async function logout() {
    try { await api('/api/logout', { method: 'POST' }); } catch { /* Clear local view even if session expired. */ }
    const timerState = useTimerStore.getState();
    timerState.reset('focus', timerState.durations?.focus || 25);
    timerState.setSubject('');
    setCsrfToken(''); setUser(null); setDashboard({ subjects: [], projects: [], schedule: [], stats: {}, preferences: {} });
  }
  async function perform(task, successMessage) {
    try { await task(); await refreshDashboard(); if (successMessage) showToast(successMessage); }
    catch (err) { showToast(err.message, 'error'); throw err; }
  }
  const createProject = (body) => perform(() => api('/api/projects', { method: 'POST', body }), 'Project created');
  const updateProject = (id, body) => perform(() => api(`/api/projects/${id}`, { method: 'PATCH', body }), 'Project updated');
  const addProjectTag = (projectId, name) => perform(() => api(`/api/projects/${projectId}/tags`, { method: 'POST', body: { name } }), 'Tag added');
  const addTask = (projectId, body) => perform(() => api(`/api/projects/${projectId}/tasks`, { method: 'POST', body: typeof body === 'string' ? { title: body } : body }), 'Task added');
  const updateTask = (id, body) => perform(() => api(`/api/tasks/${id}`, { method: 'PATCH', body }), 'Task updated');
  const toggleTask = (task) => perform(() => api(`/api/tasks/${task.id}`, { method: 'PATCH', body: { status: task.status === 'done' ? 'todo' : 'done' } }), 'Task updated');
  const deleteTask = async (id) => { if (window.confirm('Delete this task?')) await perform(() => api(`/api/tasks/${id}`, { method: 'DELETE' }), 'Task deleted'); };
  const deleteProject = async (id) => { if (window.confirm('Delete this project and its tasks?')) await perform(() => api(`/api/projects/${id}`, { method: 'DELETE' }), 'Project deleted'); };
  const createCourse = (body) => perform(() => api('/api/subjects', { method: 'POST', body }), 'Course added');
  const updateCourse = (id, body) => perform(() => api(`/api/subjects/${id}`, { method: 'PATCH', body }), 'Course updated');
  const deleteCourse = async (id) => { if (window.confirm('Delete this course and its study logs?')) await perform(() => api(`/api/subjects/${id}`, { method: 'DELETE' }), 'Course deleted'); };
  const createEvent = (body) => perform(() => api('/api/schedule', { method: 'POST', body }), 'Schedule block added');
  const updateEvent = (id, body) => perform(() => api(`/api/schedule/${id}`, { method: 'PATCH', body }), 'Schedule block updated');
  const deleteEvent = (id) => perform(() => api(`/api/schedule/${id}`, { method: 'DELETE' }), 'Schedule block removed');
  const manualLog = (body) => perform(() => api('/api/log-hours', { method: 'POST', body }), 'Study time logged');
  const savePreferences = (body) => perform(() => api('/api/preferences', { method: 'PUT', body }), 'Preferences saved');
  const saveProfile = async (body) => {
    try {
      const result = await api('/api/profile', { method: 'PATCH', body });
      setUser(result.user);
      showToast('Profile updated');
    } catch (err) { showToast(err.message, 'error'); throw err; }
  };
  const deleteResource = async (id, reload) => { if (window.confirm('Delete this resource?')) { await api(`/api/resources/${id}`, { method: 'DELETE' }); await reload(); showToast('Resource deleted'); } };

  const addRecommendationToTimeline = useCallback(async (card) => {
    const duration = card.type === 'recharge' ? 15 : Number(card.duration_minutes || 50);
    let start = card.suggested_start_time ? new Date(card.suggested_start_time) : null;
    if (!start || Number.isNaN(start.getTime())) {
      const now = new Date();
      start = new Date(`${scheduleDate}T10:00:00`);
      if (scheduleDate === localDate()) {
        start = new Date(now);
        start.setMinutes(Math.ceil((start.getMinutes() + 1) / 15) * 15, 0, 0);
      }
      const dayEnd = new Date(`${scheduleDate}T17:00:00`);
      while (start < dayEnd) {
        const endCandidate = new Date(start.getTime() + duration * 60000);
        if (endCandidate > dayEnd) break;
        const conflict = dashboard.schedule.find((event) => {
          const eventStart = new Date(event.start_time);
          const eventEnd = new Date(event.end_time);
          return eventStart < endCandidate && eventEnd > start;
        });
        if (!conflict) break;
        start = new Date(conflict.end_time);
        start.setMinutes(Math.ceil(start.getMinutes() / 15) * 15, 0, 0);
      }
    }
    const dayEnd = new Date(`${scheduleDate}T17:00:00`);
    const end = new Date(start.getTime() + duration * 60000);
    if (start >= dayEnd || end > dayEnd) {
      showToast('No open slot remains in the 10 AM–5 PM planning window for this recommendation.', 'error');
      return;
    }
    const payload = {
      title: card.type === 'recharge' ? 'Recharge break' : (card.headline || 'Focused study block'),
      start_time: localDateTime(localDateFromDate(start), start.getHours(), start.getMinutes()),
      end_time: localDateTime(localDateFromDate(end), end.getHours(), end.getMinutes()),
      event_type: card.type === 'recharge' ? 'break' : 'study',
      subject_id: card.subject_id || null,
    };
    try { await api('/api/schedule', { method: 'POST', body: payload }); await refreshDashboard(); showToast('Recommendation added to your timeline'); }
    catch (err) { showToast(err.message, 'error'); }
  }, [dashboard.schedule, scheduleDate, refreshDashboard, showToast]);

  const refreshAI = async () => { try { setRecommendations(await api(`/api/ai/recommendations?date=${encodeURIComponent(scheduleDate)}`)); showToast('Study insights refreshed'); } catch (err) { showToast(err.message, 'error'); } };
  const onAuthenticated = (nextUser) => setUser(nextUser);
  const noopTimerRefresh = useCallback(() => { refreshDashboard(); showToast('Focus session complete. Nicely done!'); }, [refreshDashboard, showToast]);

  if (authLoading) return <div className="loading-screen"><div className="brand-mark"><Sparkles size={21} /></div><span>Preparing your study space…</span></div>;
  if (!user) return <><AuthScreen onAuthenticated={onAuthenticated} /><Toast toast={toast} onClose={() => setToast(null)} /></>;

  return <div className="app-shell">
    <Sidebar page={page} setPage={setPage} user={user} subjects={dashboard.subjects} onLogout={logout} onTimerComplete={noopTimerRefresh} />
    <DndContext onDragEnd={(event) => { if (event.over?.id === 'schedule-drop-zone' && event.active.data.current?.card) addRecommendationToTimeline(event.active.data.current.card); }}>
    <main className="main-area"><Topbar user={user} stats={dashboard.stats} page={page} unreadCount={unreadNotifications} onNotificationsClick={() => setPage('productivity')} />
      {loading && <div className="refresh-line"><span />Refreshing your workspace</div>}
      {page === 'dashboard' && <div className="workspace-grid">
        <ProjectsPanel projects={dashboard.projects} onCreateProject={createProject} onEditProject={updateProject} onAddTask={addTask} onUpdateTask={updateTask} onToggleTask={toggleTask} onDeleteTask={deleteTask} onDeleteProject={deleteProject} onAddTag={addProjectTag} subjects={dashboard.subjects} onCreateCourse={createCourse} onUpdateCourse={updateCourse} onDeleteCourse={deleteCourse} />
        <SchedulePanel events={dashboard.schedule} projects={dashboard.projects} subjects={dashboard.subjects} onCreateEvent={createEvent} onUpdateEvent={updateEvent} onDeleteEvent={deleteEvent} onManualLog={manualLog} onReload={refreshDashboard} selectedDate={scheduleDate} onDateChange={setScheduleDate} />
        <AIHub recommendations={recommendations} onAdd={addRecommendationToTimeline} onRefresh={refreshAI} />
      </div>}
      {page === 'projects' && <div className="single-page-grid"><ProjectsPanel projects={dashboard.projects} onCreateProject={createProject} onEditProject={updateProject} onAddTask={addTask} onUpdateTask={updateTask} onToggleTask={toggleTask} onDeleteTask={deleteTask} onDeleteProject={deleteProject} onAddTag={addProjectTag} subjects={dashboard.subjects} onCreateCourse={createCourse} onUpdateCourse={updateCourse} onDeleteCourse={deleteCourse} /><div className="panel side-note-panel"><div className="note-illustration"><GraduationCap size={30} /></div><span className="eyebrow">A SMALL REMINDER</span><h2>Progress over perfection.</h2><p>Break ambitious goals into tasks you can complete in one sitting. Every checked box is momentum.</p></div></div>}
      {page === 'schedule' && <div className="single-page-grid"><SchedulePanel events={dashboard.schedule} projects={dashboard.projects} subjects={dashboard.subjects} onCreateEvent={createEvent} onUpdateEvent={updateEvent} onDeleteEvent={deleteEvent} onManualLog={manualLog} onReload={refreshDashboard} selectedDate={scheduleDate} onDateChange={setScheduleDate} /><div className="panel side-note-panel"><div className="note-illustration"><Clock3 size={28} /></div><span className="eyebrow">TIME WITH INTENTION</span><h2>Give your focus a home.</h2><p>Schedule a realistic block, leave breathing room between sessions, and protect time to recharge.</p><div className="mini-stat"><strong>{dashboard.stats.sessions_today || 0}</strong><span>focus sessions today</span></div></div></div>}
      {page === 'ai' && <div className="single-page-grid ai-page-grid"><AIHub recommendations={recommendations} onAdd={addRecommendationToTimeline} onRefresh={refreshAI} page="ai" /><section className="panel insight-detail"><SectionTitle eyebrow="WHY AURA SUGGESTS THIS" title="Your study signals" /><p className="panel-description">AURA combines exam proximity, course difficulty, remaining target hours, revision gaps, and recorded focus sessions. Gemini can add natural-language coaching when configured; the rule-based engine remains available as a fallback.</p><div className="signal-list">{(recommendations?.analysis || []).map((item) => <div className="signal-row" key={item.id}><div><strong>{item.name}</strong><span>{item.days_left < 0 ? 'Exam date passed' : `${item.days_left} days to exam`} · Difficulty {item.difficulty}/5</span></div><div className="signal-score"><small>PRIORITY</small><b>{Math.round(item.priority_score)}</b></div></div>)}</div>{(recommendations?.recommendations || []).map((r, i) => <div className="warning-note" key={i}><Activity size={15} />{r}</div>)}</section></div>}
      {page === 'resources' && <ResourceBank projects={dashboard.projects} onRefresh={refreshDashboard} onDelete={deleteResource} showToast={showToast} />}
      {page === 'groups' && <StudyGroupsPage showToast={showToast} />}
      {page === 'learning' && <LearningHub subjects={dashboard.subjects} onDataChanged={refreshDashboard} showToast={showToast} />}
      {page === 'productivity' && <ProductivityHub showToast={showToast} onUnreadChange={setUnreadNotifications} onSaveGoal={(value) => savePreferences({ daily_goal_hours: value })} />}
      {page === 'settings' && <SettingsPanel user={user} preferences={dashboard.preferences || {}} onSaveProfile={saveProfile} onSavePreferences={savePreferences} />}
      <footer className="app-footer"><span>✦ AURA Study</span><span>Designed for steady progress, not pressure.</span></footer>
    </main>
    </DndContext>
    <Toast toast={toast} onClose={() => setToast(null)} />
  </div>;
}

function localDateFromDate(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }

export default App;
