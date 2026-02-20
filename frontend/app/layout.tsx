import './globals.css';

const brandFavicon =
  'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22%232D2D2D%22 stroke-width=%222%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22><path d=%22M12 2L2 22h20L12 2z%22/><path d=%22M6.5 13.5c2.5-2.5 7.5-2.5 11 0%22/></svg>';

export const metadata = {
  title: 'ArcBrief',
  description: 'Paper-like minimal interface for ArcBrief',
  icons: {
    icon: brandFavicon,
    shortcut: brandFavicon,
    apple: brandFavicon,
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Merriweather:ital,wght@0,300;0,400;0,700;0,900;1,300;1,400&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}