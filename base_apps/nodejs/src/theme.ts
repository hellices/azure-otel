"use client";

import { createTheme, MantineColorsTuple } from "@mantine/core";

const azure: MantineColorsTuple = [
  "#e6f4ff",
  "#cfe6ff",
  "#a3cdff",
  "#74b1ff",
  "#4d99ff",
  "#3389fe",
  "#2581fe",
  "#176fe4",
  "#0061cc",
  "#0055b3",
];

export const theme = createTheme({
  primaryColor: "azure",
  colors: { azure },
  defaultRadius: "md",
  fontFamily:
    'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
});
