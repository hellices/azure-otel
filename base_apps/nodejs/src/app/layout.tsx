import type { Metadata, Viewport } from "next";
import {
  ColorSchemeScript,
  MantineProvider,
  mantineHtmlProps,
} from "@mantine/core";
import { Notifications } from "@mantine/notifications";

import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "./globals.css";

import { theme } from "@/theme";

export const metadata: Metadata = {
  title: "Azure Observability — Sketch Apps",
  description:
    "Three small services to practice Azure observability (logs, metrics, traces).",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko" {...mantineHtmlProps}>
      <head>
        <ColorSchemeScript defaultColorScheme="auto" />
        {/* Loaded synchronously so window.__APP_CONFIG__ is available before any client bundle runs */}
        <script src="/config.js" />
      </head>
      <body>
        <MantineProvider theme={theme} defaultColorScheme="auto">
          <Notifications position="top-right" />
          {children}
        </MantineProvider>
      </body>
    </html>
  );
}
