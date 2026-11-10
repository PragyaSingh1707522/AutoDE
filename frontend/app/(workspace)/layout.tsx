import WorkspaceShell from '../../components/workspace-shell';

export default function AuthenticatedLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <WorkspaceShell>{children}</WorkspaceShell>;
}
