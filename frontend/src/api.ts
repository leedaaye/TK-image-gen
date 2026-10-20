export type ProductImage = { id: string; url: string; role: string; filename: string };
export type Product = { id: string; name: string; description: string; category: string; sku: string; features: string; constraints: string; price: string | number; currency: string; created_at: string; images: ProductImage[] };
export type ProductInput = Omit<Product, 'id' | 'created_at' | 'images'>;
export type Version = { id: string; url: string; base_url: string; created_at: string; instruction: string };
export type Slide = { id: string; position: number; title: string; body: string; prompt: string; status: 'pending' | 'queued' | 'generating' | 'ready' | 'failed'; error: string; selected_version_id: string | null; url: string | null; versions: Version[] };
export type Project = { id: string; title: string; product_id: string; product_name: string; market: string; language: string; image_count: number; style: string; brief: string; auto_generate: boolean; status: 'planning' | 'draft' | 'generating' | 'ready' | 'failed'; caption: string; tags: string[]; analysis: Record<string, unknown>; error: string; created_at: string; slides: Slide[] };
export type ProjectInput = { product_id: string; market: string; language: string; image_count: number; style: string; brief: string; auto_generate: boolean };
export type Provider = { base_url: string; model: string; api_key: string; has_key: boolean; clear_key?: boolean; timeout: number; concurrency: number; mode: 'reference' | 'background'; extra: Record<string, unknown> };
export type Settings = { analysis: Provider; image: Provider };
export type Task = { id: string; project_id: string; slide_id: string | null; type: 'plan' | 'image'; status: 'queued' | 'running' | 'completed' | 'failed'; error: string; created_at: string; updated_at: string };
export type Health = { status: string; database: string; worker_alive: boolean };
export type Auth = { authenticated: boolean; setup_required: boolean };

export class ApiError extends Error { constructor(message: string, public status: number) { super(message); } }
export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, { credentials: 'same-origin', ...options, headers: { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...options.headers } });
  if (!response.ok) {
    let detail = `请求失败（${response.status}）`;
    try { const data = await response.json(); detail = typeof data.detail === 'string' ? data.detail : Array.isArray(data.detail) ? data.detail.map((item: { loc?: (string | number)[]; msg?: string }) => `${item.loc?.filter(part => part !== 'body').join(' / ') || '输入内容'}：${item.msg || '格式不正确'}`).join('；') : '请求未成功，请检查填写内容后重试'; } catch { /* keep status fallback */ }
    if (response.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('session-expired'));
    throw new ApiError(detail, response.status);
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return text ? JSON.parse(text) as T : undefined as T;
}
export const api = {
  auth: () => request<Auth>('/auth/status'),
  authenticate: (password: string, setup: boolean) => request('/auth/' + (setup ? 'setup' : 'login'), { method: 'POST', body: JSON.stringify({ password }) }),
  logout: () => request('/auth/logout', { method: 'POST' }),
  health: () => request<Health>('/health'),
  products: () => request<Product[]>('/products'),
  saveProduct: (input: ProductInput, id?: string) => request<Product>(id ? `/products/${id}` : '/products', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(input) }),
  deleteProduct: (id: string) => request(`/products/${id}`, { method: 'DELETE' }),
  upload: (id: string, files: File[]) => { const body = new FormData(); files.forEach(file => body.append('files', file)); return request<Product>(`/products/${id}/images`, { method: 'POST', body }); },
  imageRole: (id: string, imageId: string, role: string) => request<Product>(`/products/${id}/images/${imageId}`, { method: 'PATCH', body: JSON.stringify({ role }) }),
  deleteImage: (id: string, imageId: string) => request<Product>(`/products/${id}/images/${imageId}`, { method: 'DELETE' }),
  projects: () => request<Project[]>('/projects'),
  project: (id: string) => request<Project>(`/projects/${id}`),
  createProject: (input: ProjectInput) => request<Project>('/projects', { method: 'POST', body: JSON.stringify(input) }),
  updateProject: (id: string, input: Partial<Pick<Project, 'title' | 'caption' | 'tags' | 'style'>> & { slides?: Pick<Slide, 'id' | 'title' | 'body' | 'prompt'>[] }) => request<Project>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(input) }),
  generate: (id: string, slide_ids?: string[]) => request<Project>(`/projects/${id}/generate`, { method: 'POST', body: JSON.stringify(slide_ids ? { slide_ids } : {}) }),
  replan: (id: string) => request<Project>(`/projects/${id}/replan`, { method: 'POST' }),
  regenerate: (id: string, slide: string, instruction: string) => request<Project>(`/projects/${id}/slides/${slide}/regenerate`, { method: 'POST', body: JSON.stringify({ instruction }) }),
  updateSlide: (id: string, slide: string, input: Partial<Pick<Slide, 'title' | 'body' | 'selected_version_id'>>) => request<Project>(`/projects/${id}/slides/${slide}`, { method: 'PATCH', body: JSON.stringify(input) }),
  deleteProject: (id: string) => request(`/projects/${id}`, { method: 'DELETE' }),
  tasks: () => request<Task[]>('/tasks'),
  retry: (id: string) => request<Task>(`/tasks/${id}/retry`, { method: 'POST' }),
  settings: () => request<Settings>('/settings'),
  saveSettings: (input: Settings) => request<Settings>('/settings', { method: 'PUT', body: JSON.stringify(input) }),
  test: (kind: 'analysis' | 'image') => request<{ ok: boolean; message: string }>(`/settings/test/${kind}`, { method: 'POST' }),
};

export async function downloadProject(project: Project, ids: string[], includeBases: boolean) {
  const params = new URLSearchParams({ slide_ids: ids.join(','), include_bases: String(includeBases) });
  const response = await fetch(`/api/projects/${project.id}/export?${params}`, { credentials: 'same-origin' });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail || '下载失败，请稍后重试');
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = `${project.title || project.product_name || '图文作品'}.zip`; anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
