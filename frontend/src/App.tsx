import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { ArrowRight, Bell, ChevronRight, CircleHelp, Command, LayoutDashboard, LogOut, Menu, Package, Plus, Search, Settings2, ShieldCheck, Sparkles, WandSparkles, Workflow, X, Zap, Activity, ArrowUpRight } from 'lucide-react';
import { api, type Auth, type Health, type Product, type Project, type Task } from './api';
import { Empty, ErrorBox, errorMessage, formatDate, Spinner, Status } from './ui';
import Products from './Products';
import Studio from './Studio';
import ModelSettings from './ModelSettings';

type Page = 'overview' | 'products' | 'studio' | 'tasks' | 'settings';
const navigation: { id: Page; label: string; icon: typeof Package; description: string }[] = [
  { id: 'overview', label: '工作台总览', icon: LayoutDashboard, description: '每一个好创意，都从这里开始' },
  { id: 'products', label: '商品库', icon: Package, description: '管理商品信息，让创作有据可依' },
  { id: 'studio', label: '生成工作台', icon: WandSparkles, description: '从商品灵感，到完整图文作品' },
  { id: 'tasks', label: '任务中心', icon: Workflow, description: '创作持续运行，进度尽在掌握' },
  { id: 'settings', label: '模型设置', icon: Settings2, description: '连接你的 AI 创作引擎' },
];

function AuthScreen({ setup, onLogin }: { setup: boolean; onLogin: () => void }) {
  const [password, setPassword] = useState(''); const [confirm, setConfirm] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function submit(event: FormEvent) { event.preventDefault(); if (setup && password !== confirm) { setError('两次输入的密码不一致'); return; } setBusy(true); setError(''); try { await api.authenticate(password, setup); onLogin(); } catch (err) { setError(errorMessage(err)); } finally { setBusy(false); } }
  return <div className="auth-layout"><div className="auth-story"><a className="brand" href="/" aria-label="TK Studio"><div className="brand-mark"><Sparkles size={25} /></div><span>TK<span className="brand-light"> Studio</span><small>图文创作工作台</small></span></a><div className="auth-story-content"><span className="eyebrow">IDEAS INTO IMPACT</span><h1>让好商品，<br />拥有好内容<span>。</span></h1><p>把商品、灵感与 AI 创作连接起来。<br />为你的下一次出海，准备一组出色的图文。</p><div className="auth-art"><div className="art-card art-card-back"><div className="art-lines" /></div><div className="art-card art-card-front"><div className="art-product"><Package size={64} strokeWidth={1} /></div><span>MADE TO STAND OUT</span><strong>让细节，被看见。</strong><div className="art-dots"><i /><i /><i /></div></div><div className="art-spark"><Sparkles size={25} /></div></div></div><small className="auth-footer">TK STUDIO / YOUR CREATIVE WORKSPACE</small></div><main className="auth-panel"><div className="auth-form"><div className="pill"><ShieldCheck size={14} /> 专属安全工作空间</div><h2>{setup ? '创建你的工作空间' : '欢迎回到工作台'}</h2><p>{setup ? '首次使用，请设置管理员密码，开启创作之旅。' : '输入管理员密码，继续你的创作。'}</p><form onSubmit={submit}><label className="field"><span>{setup ? '设置管理员密码' : '管理员密码'}</span><input autoFocus required minLength={setup ? 10 : 1} type="password" autoComplete={setup ? 'new-password' : 'current-password'} placeholder={setup ? '至少 10 位，建议包含字母与数字' : '请输入你的密码'} value={password} onChange={e => setPassword(e.target.value)} /></label>{setup && <label className="field"><span>确认密码</span><input required type="password" autoComplete="new-password" placeholder="再次输入管理员密码" value={confirm} onChange={e => setConfirm(e.target.value)} /></label>}<ErrorBox message={error} /><button className="button primary auth-submit" disabled={busy}>{busy ? '正在进入…' : setup ? '创建并进入工作台' : '进入工作台'}<ArrowRight size={18} /></button></form><div className="auth-note"><ShieldCheck size={16} />{setup ? '单管理员模式 · 密码加密存储' : '私有部署 · 你的数据由你掌控'}</div></div><p className="auth-bottom">灵感就位，随时开工。<Sparkles size={15} /></p></main></div>;
}

export default function App() {
  const [auth, setAuth] = useState<Auth | null>(null); const [authError, setAuthError] = useState(''); const [page, setPage] = useState<Page>('overview'); const [mobile, setMobile] = useState(false);
  const [products, setProducts] = useState<Product[]>([]); const [projects, setProjects] = useState<Project[]>([]); const [tasks, setTasks] = useState<Task[]>([]); const [health, setHealth] = useState<Health | null>(null); const [loading, setLoading] = useState(true); const [loadError, setLoadError] = useState(''); const [notice, setNotice] = useState(''); const [selectedProject, setSelectedProject] = useState<string | null>(null); const [createToken, setCreateToken] = useState(0);
  const notify = useCallback((message: string) => setNotice(message), []);
  const refresh = useCallback(async (quiet = false) => {
    try { const [nextProducts, nextProjects, nextTasks, nextHealth] = await Promise.all([api.products(), api.projects(), api.tasks(), api.health()]); setProducts(nextProducts); setProjects(nextProjects); setTasks(nextTasks); setHealth(nextHealth); setLoadError(''); } catch (err) { if (!quiet) setLoadError(errorMessage(err)); } finally { setLoading(false); }
  }, []);
  useEffect(() => { api.auth().then(setAuth).catch(err => setAuthError(errorMessage(err))); const expired = () => setAuth({ authenticated: false, setup_required: false }); window.addEventListener('session-expired', expired); return () => window.removeEventListener('session-expired', expired); }, []);
  useEffect(() => { if (!auth?.authenticated) return; void refresh(); const timer = window.setInterval(() => void refresh(true), 3000); return () => window.clearInterval(timer); }, [auth?.authenticated, refresh]);
  useEffect(() => { if (!notice) return; const timer = window.setTimeout(() => setNotice(''), 4500); return () => window.clearTimeout(timer); }, [notice]);
  const navigate = (next: Page) => { setPage(next); setMobile(false); };
  const openProject = (id: string) => { setSelectedProject(id); navigate('studio'); };
  const newProject = () => { setCreateToken(token => token + 1); navigate('studio'); };
  if (!auth) return <div className="boot"><div className="brand-mark"><Sparkles size={28} /></div>{authError ? <><ErrorBox message={authError} /><button className="button" onClick={() => window.location.reload()}>重新连接</button></> : <Spinner />}</div>;
  if (!auth.authenticated) return <AuthScreen setup={auth.setup_required} onLogin={() => { setLoading(true); setAuth({ authenticated: true, setup_required: false }); }} />;
  const currentNav = navigation.find(item => item.id === page)!;
  const activeTasks = tasks.filter(task => ['running', 'queued'].includes(task.status));
  return <div className="app-shell">
    {mobile && <div className="sidebar-scrim" onClick={() => setMobile(false)} />}
    <aside className={`sidebar ${mobile ? 'sidebar-open' : ''}`}>
      <a className="brand" href="#" onClick={e => { e.preventDefault(); navigate('overview'); }}>
        <div className="brand-mark"><Sparkles size={24} /></div>
        <span>TK<span className="brand-light"> Studio</span><small>图文创作工作台</small></span>
      </a>
      <button className="button primary sidebar-create" onClick={newProject}>
        <Plus size={18} />新建图文项目
      </button>
      <div className="nav-caption">工作空间</div>
      <nav>
        {navigation.map(item => (
          <button key={item.id} className={`nav-item ${page === item.id ? 'active' : ''}`} onClick={() => navigate(item.id)}>
            <item.icon size={19} />
            <span>{item.label}</span>
            {item.id === 'tasks' && activeTasks.length > 0 && <b>{activeTasks.length}</b>}
            {page === item.id && <ChevronRight size={15} />}
          </button>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="creative-note">
          <div><Zap size={17} /><span>为创意，留出更多时间</span></div>
          <p>独立任务持续执行<br />关闭页面，也不打断灵感。</p>
          <span className={`worker-state ${health?.worker_alive ? 'online' : ''}`}>
            <i />{health?.worker_alive ? '创作引擎运行中' : '等待 Worker 连接'}
          </span>
        </div>
        <button className="profile" onClick={async () => { try { await api.logout(); setAuth({ authenticated: false, setup_required: false }); } catch (err) { notify(errorMessage(err)); } }}>
          <span className="avatar">A</span>
          <span><strong>管理员</strong><small>专属创作空间</small></span>
          <LogOut size={16} />
        </button>
      </div>
    </aside>
    <div className="main-shell">
      <header className="topbar">
        <div className="breadcrumb">
          <button className="icon-button menu-toggle" onClick={() => setMobile(true)} aria-label="打开导航">
            <Menu size={21} />
          </button>
          <span>工作空间</span>
          <ChevronRight size={14} />
          <strong>{currentNav.label}</strong>
        </div>
        <div className="topbar-right">
          <button className="icon-button" title="查看任务" onClick={() => navigate('tasks')} aria-label="查看任务">
            <Bell size={18} />
            {activeTasks.length > 0 && <i className="notification-dot" />}
          </button>
          <span className="avatar small">A</span>
        </div>
      </header>
      <main className="main-content">
        {loadError && (
          <div className="connection-error">
            <ErrorBox message={loadError} />
            <button className="button small-button" onClick={() => void refresh()}>重新连接</button>
          </div>
        )}
        {loading ? <Spinner /> : <>
          {page === 'overview' && <Overview products={products} projects={projects} tasks={tasks} newProject={newProject} openProject={openProject} navigate={navigate} />}
          {page === 'products' && <Products products={products} refresh={refresh} notify={notify} />}
          {page === 'studio' && <Studio products={products} projects={projects} selectedId={selectedProject} onSelect={setSelectedProject} createToken={createToken} refresh={refresh} notify={notify} />}
          {page === 'tasks' && <Tasks tasks={tasks} projects={projects} openProject={openProject} refresh={refresh} notify={notify} />}
          {page === 'settings' && <ModelSettings notify={notify} />}
        </>}
      </main>
      <footer className="main-footer">
        <span>用灵感连接商品与世界</span>
        <span>TK Studio <i /> Private workspace</span>
      </footer>
    </div>
    {notice && (
      <div className="toast" role="status">
        <CircleHelp size={18} />
        {notice}
        <button onClick={() => setNotice('')} aria-label="关闭提示"><X size={15} /></button>
      </div>
    )}
  </div>;
}

function Overview({ products, projects, tasks, newProject, openProject, navigate }: { products: Product[]; projects: Project[]; tasks: Task[]; newProject: () => void; openProject: (id: string) => void; navigate: (page: Page) => void }) {
  const readyImages = projects.reduce((total, project) => total + project.slides.filter(slide => slide.status === 'ready').length, 0);
  const stats: { label: string; value: number; icon: ReactNode; note: string; color: string }[] = [
    { label: '我的商品', value: products.length, icon: <Package size={21} />, note: '沉淀每一份商品资产', color: 'purple' },
    { label: '创作项目', value: projects.length, icon: <WandSparkles size={21} />, note: '让灵感变成系列内容', color: 'blue' },
    { label: '已生成图片', value: readyImages, icon: <Sparkles size={21} />, note: '高品质内容，随时可用', color: 'orange' },
    { label: '进行中任务', value: tasks.filter(task => ['running', 'queued'].includes(task.status)).length, icon: <Activity size={21} />, note: '创作引擎持续运行', color: 'green' },
  ];
  return <><section className="hero-banner"><div className="hero-content"><span className="hero-label"><Sparkles size={14} /> YOUR NEXT GREAT STORY</span><h2>好商品，值得被更多人看见。</h2><p>从商品洞察到视觉表达，<br className="mobile-break" />让 AI 为你的出海创作提速。</p><button className="button hero-button" onClick={newProject}>开启新的创作<ArrowRight size={17} /></button></div><div className="hero-visual" aria-hidden="true"><div className="hero-orbit orbit-one" /><div className="hero-orbit orbit-two" /><div className="mini-card card-one"><div className="mini-icon"><Package size={38} strokeWidth={1.2} /></div><span>PRODUCT STORY</span><div className="mini-line" /><div className="mini-line short" /></div><div className="mini-card card-two"><Sparkles size={25} /><span>CREATE<br /><strong>SOMETHING<br />GREAT.</strong></span><i /></div><div className="floating-badge"><Zap size={15} fill="currentColor" />灵感，正在发生</div></div></section><div className="stats-grid">{stats.map(stat => <div className="stat-card" key={stat.label}><div className="stat-top"><span>{stat.label}</span><div className={`stat-icon ${stat.color}`}>{stat.icon}</div></div><strong>{stat.value}<small>{stat.label === '已生成图片' ? '张' : stat.label === '我的商品' ? '件' : '个'}</small></strong><p>{stat.note}</p></div>)}</div><div className="overview-columns"><section className="panel recent-panel"><div className="panel-heading"><div><h2>最近的创作</h2><p>继续打磨你的下一个出色作品</p></div><button className="text-button" onClick={() => navigate('studio')}>全部项目<ArrowUpRight size={15} /></button></div>{projects.length === 0 ? <Empty title="你的第一份作品，从这里开始" description="选择一个商品，让 AI 帮你策划与创作整组图文。" icon="sparkle" action={<button className="button" onClick={newProject}><Plus size={16} />创建图文项目</button>} /> : <div className="recent-list">{projects.slice(0, 5).map(project => <button className="recent-item" key={project.id} onClick={() => openProject(project.id)}><div className="project-thumb">{project.slides.find(slide => slide.url)?.url ? <img src={project.slides.find(slide => slide.url)!.url!} alt="项目预览" /> : <WandSparkles size={23} />}</div><div className="recent-info"><strong>{project.title || project.product_name}</strong><span>{project.market} · {project.language} · {project.image_count} 张图片</span></div><div className="recent-status"><Status status={project.status} /><small>{formatDate(project.created_at)}</small></div><ChevronRight size={16} /></button>)}</div>}</section><section className="panel workflow-panel"><div className="panel-heading"><div><h2>创作只需三步</h2><p>让每一步，都更简单</p></div><Command size={18} /></div><div className="workflow-step"><span>01</span><div><h3>准备你的商品</h3><p>录入真实卖点，上传多角度参考图</p></div><Package size={19} /></div><div className="workflow-step"><span>02</span><div><h3>让灵感有方向</h3><p>选择市场与风格，确认图文策划</p></div><WandSparkles size={19} /></div><div className="workflow-step"><span>03</span><div><h3>把创意变成作品</h3><p>逐图优化，打包下载，即刻可用</p></div><Sparkles size={19} /></div><div className="tip"><ShieldCheck size={17} /><p>真实，是好内容的底色。<br /><span>AI 基于商品事实创作，不编造参数与功效。</span></p></div></section></div></>;
}

function Tasks({ tasks, projects, openProject, refresh, notify }: { tasks: Task[]; projects: Project[]; openProject: (id: string) => void; refresh: (quiet?: boolean) => Promise<void>; notify: (message: string) => void }) {
  const [filter, setFilter] = useState('all'); const [busy, setBusy] = useState<string | null>(null); const [query, setQuery] = useState('');
  const rows = tasks.filter(task => (filter === 'all' || (filter === 'active' ? ['running', 'queued'].includes(task.status) : task.status === filter)) && `${projects.find(p => p.id === task.project_id)?.title || ''} ${task.id}`.toLowerCase().includes(query.toLowerCase()));
  return <section className="panel"><div className="list-toolbar"><div className="tabs">{[['all', '全部任务'], ['active', '进行中'], ['completed', '已完成'], ['failed', '失败任务']].map(([value, label]) => <button className={filter === value ? 'active' : ''} key={value} onClick={() => setFilter(value)}>{label}</button>)}</div><div className="search-box"><Search size={17} /><input placeholder="搜索项目或任务 ID" value={query} onChange={e => setQuery(e.target.value)} /></div></div><div className="poll-note"><span className="live-dot" />每 3 秒自动同步 · 任务由独立 Worker 持续执行</div>{rows.length === 0 ? <Empty title="这里暂时没有任务" description="创建图文项目后，策划与生图进度会显示在这里。" icon="sparkle" /> : <div className="table-scroll"><table><thead><tr><th>任务 / 项目</th><th>任务类型</th><th>状态</th><th>更新时间</th><th>操作</th></tr></thead><tbody>{rows.map(task => <tr key={task.id}><td><button className="table-link" onClick={() => openProject(task.project_id)}>{projects.find(p => p.id === task.project_id)?.title || '图文项目'}</button><small className="mono">{task.id.slice(0, 8)}{task.error && <span className="task-error" title={task.error}>{task.error}</span>}</small></td><td><span className="type-tag">{task.type === 'plan' ? '内容策划' : '图片生成'}</span></td><td><Status status={task.status} /></td><td className="muted">{formatDate(task.updated_at)}</td><td>{task.status === 'failed' ? <button className="text-button" disabled={busy === task.id} onClick={async () => { setBusy(task.id); try { await api.retry(task.id); await refresh(true); notify('任务已重新排队'); } catch (err) { notify(errorMessage(err)); } finally { setBusy(null); } }}>重新尝试</button> : <button className="text-button muted" onClick={() => openProject(task.project_id)}>查看项目<ChevronRight size={14} /></button>}</td></tr>)}</tbody></table></div>}</section>;
}
