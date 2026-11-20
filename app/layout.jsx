import './globals.css';
export const metadata = { title: '서울상권 인사이트' };
export default function RootLayout({ children }) {
  return <html lang="ko"><head>
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700&display=swap" />
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=block" />
    <style>{'.material-symbols-outlined,.material-symbols-rounded,.material-symbols-sharp,.material-icons{display:inline-block;width:1em;height:1em;line-height:1!important;box-sizing:content-box;overflow:hidden;white-space:nowrap;direction:ltr;vertical-align:middle}'}</style>
  </head><body>{children}</body></html>;
}
