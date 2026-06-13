import type { Metadata } from "next";
import "./globals.css";
import Provider from "@/components/Provider";
import Navbar from "@/components/Navbar";

export const metadata: Metadata = {
  title: "Challenge AI - Jockey & Driver Pricing Dashboard",
  description:
    "AI-powered pricing dashboard for Australian Jockey and Driver Challenges",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  var theme = localStorage.getItem('theme');
                  if (theme === 'dark' || !theme) {
                    document.documentElement.classList.add('dark');
                  } else {
                    document.documentElement.classList.remove('dark');
                  }
                } catch(e) {}
              })();
            `,
          }}
        />
      </head>
      <body>
        <Provider>
          <Navbar />
          <main className="lg:pl-64 pb-16 lg:pb-0 min-h-screen">
            <div className="max-w-7xl mx-auto p-4 md:p-6 lg:p-8">
              {children}
            </div>
          </main>
        </Provider>
      </body>
    </html>
  );
}
