/**
 * App shell — Aurora Glass design system.
 * Fixed glass dock (Sidebar) on the left, slim glass top bar, aurora mesh
 * backdrop behind everything.
 */
import { useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';
import Header from './Header';
import Footer from './Footer';

interface LayoutProps {
  children: React.ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();

  return (
    <div className="min-h-screen overflow-x-hidden">
      <div className="aurora-bg" aria-hidden="true" />
      <Sidebar />
      {/* Content shifted right of the dock (72px rail / 224px expanded + gutters) */}
      <div className="pl-[104px] xl:pl-[256px] pr-4 flex flex-col min-h-screen">
        <Header />
        {/* keyed on pathname → soft page-transition animation on every route change */}
        <main key={location.pathname} className="flex-1 animate-page-enter">
          {children}
        </main>
        <Footer compact />
      </div>
    </div>
  );
}
