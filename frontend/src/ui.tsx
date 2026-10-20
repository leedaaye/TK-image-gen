import { useEffect, type ReactNode } from 'react';
import { X, LoaderCircle, Package, Sparkles, CircleCheck, CircleAlert, Clock3 } from 'lucide-react';

export const statusText: Record<string, string> = { planning: '策划中', draft: '待确认', generating: '生成中', ready: '已完成', failed: '失败', pending: '待生成', queued: '排队中', running: '执行中', completed: '已完成' };
export const busyStatus = (status: string) => ['planning', 'generating', 'queued', 'running'].includes(status);
export const formatDate = (value: string) => value ? new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) : '—';
export function Status({ status }: { status: string }) {
  const Icon = busyStatus(status) ? LoaderCircle : ['ready', 'completed'].includes(status) ? CircleCheck : status === 'failed' ? CircleAlert : Clock3;
  return <span className={`status status-${status}`}><Icon size={13} className={busyStatus(status) ? 'spin' : ''} />{statusText[status] || status}</span>;
}
export function Spinner({ text = '正在加载工作空间…' }: { text?: string }) { return <div className="loading"><LoaderCircle size={25} className="spin" /><span>{text}</span></div>; }
export function Empty({ title, description, action, icon = 'product' }: { title: string; description: string; action?: ReactNode; icon?: 'product' | 'sparkle' }) { return <div className="empty"><div className="empty-icon">{icon === 'product' ? <Package size={31} /> : <Sparkles size={31} />}</div><h3>{title}</h3><p>{description}</p>{action}</div>; }
export function Modal({ title, subtitle, children, onClose, wide = false }: { title: string; subtitle?: string; children: ReactNode; onClose: () => void; wide?: boolean }) {
  useEffect(() => { const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); }; document.addEventListener('keydown', onKey); const previous = document.body.style.overflow; document.body.style.overflow = 'hidden'; return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = previous; }; }, [onClose]);
  return <div className="modal-backdrop" onClick={event => { if (event.target === event.currentTarget) onClose(); }}><section className={`modal ${wide ? 'modal-wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}><div className="modal-heading"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className="icon-button" onClick={onClose} aria-label="关闭"><X size={21} /></button></div>{children}</section></div>;
}
export function Field({ label, hint, children, className = '' }: { label: string; hint?: string; children: ReactNode; className?: string }) { return <label className={`field ${className}`}><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>; }
export function ErrorBox({ message }: { message: string }) { return message ? <div className="error-box" role="alert"><CircleAlert size={17} /><span>{message}</span></div> : null; }
export const errorMessage = (error: unknown) => error instanceof Error ? error.message : '操作失败，请稍后重试';
