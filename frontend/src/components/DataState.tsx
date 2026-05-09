import type { ReactNode } from "react";

type DataStateProps = {
  loading: boolean;
  error: string | null;
  children: ReactNode;
};

export function DataState({ loading, error, children }: DataStateProps) {
  if (loading) {
    return <div className="state-block">加载中</div>;
  }
  if (error) {
    return <div className="state-block state-error">{error}</div>;
  }
  return <>{children}</>;
}

export function EmptyState({ label = "暂无数据" }: { label?: string }) {
  return <div className="state-block">{label}</div>;
}

export function Notice({
  message,
  tone = "info",
}: {
  message: string | null;
  tone?: "info" | "error";
}) {
  if (!message) {
    return null;
  }
  return <div className={`notice notice-${tone}`}>{message}</div>;
}
