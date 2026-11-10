import './styles.css';
import './workspace.css';

export const metadata = { title: 'AutoDE', description: 'Autonomous Data Engineering for your organization' };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
