import type { Metadata, Viewport } from "next";
import "./globals.css";
import { AuthProvider } from "@/components/AuthProvider";
import ServiceWorker from "@/components/ServiceWorker";

const basePath = process.env.NEXT_BASE_PATH || "";

export const metadata: Metadata = {
  title: "StoryForge AI — AI Video Studio",
  description:
    "Turn a script into a complete multi-scene AI video. Cloud-first with a scoped local execution mode.",
  manifest: basePath
    ? `${basePath}/manifest.webmanifest`
    : "/manifest.webmanifest",
  applicationName: "StoryForge AI",
  appleWebApp: { capable: true, statusBarStyle: "black-translucent", title: "StoryForge AI" },
  icons: {
    icon: basePath ? `${basePath}/icon.svg` : "/icon.svg",
    apple: basePath ? `${basePath}/icon.svg` : "/icon.svg",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#FBFBFB" },
    { media: "(prefers-color-scheme: dark)", color: "#0A0B0D" },
  ],
  width: "device-width",
  initialScale: 1,
};

const themeBoot = `(function(){try{var t=localStorage.getItem("sf-theme");if(t==="light"){document.documentElement.classList.remove("dark")}else{document.documentElement.classList.add("dark")}}catch(e){document.documentElement.classList.add("dark")}})()`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBoot }} />
      </head>
      <body>
        <AuthProvider>{children}</AuthProvider>
        <ServiceWorker />
      </body>
    </html>
  );
}
