"use client";

import { useSyncExternalStore } from "react";
import { useTheme } from "next-themes";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const themes = [
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
];
const subscribe = () => () => {};

export function ThemeSettings() {
  const { theme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );

  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle>
          <h2>Appearance</h2>
        </CardTitle>
        <CardDescription id="theme-description">
          Choose a theme. System follows your device settings. Changes apply immediately and are
          saved in this browser.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Select
          items={themes}
          value={mounted ? theme : null}
          disabled={!mounted}
          onValueChange={(value) => {
            if (value) setTheme(value);
          }}
        >
          <SelectTrigger
            aria-label="Theme"
            aria-describedby="theme-description"
            className="sm:max-w-xs"
          >
            <SelectValue placeholder="Choose a theme" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {themes.map(({ value, label }) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
      </CardContent>
    </Card>
  );
}
