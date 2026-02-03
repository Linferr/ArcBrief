import './globals.css';

export const metadata = {
  title: 'ArcBrief',
  description: 'Apple-style UI for ArcBrief',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

