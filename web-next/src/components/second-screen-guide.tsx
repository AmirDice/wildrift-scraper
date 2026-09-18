"use client";

import { useEffect, useState } from "react";

/**
 * How to get the phone's screen in front of the reader, one route per setup.
 *
 * Every route is here because there is no way to skip this step: no mobile
 * browser implements screen capture (Chrome Android, Safari iOS, Samsung
 * Internet and Firefox Android were all unsupported as of 2026-09-17), AirPlay
 * needs a native receiver and Cast mirroring goes to a device rather than to a
 * web page. The setup cannot be removed, only moved -- so each route says
 * plainly WHAT gets installed and WHERE, and the phone never has to be the
 * answer.
 *
 * The visitor's own route is opened for them, because the fastest tutorial is
 * the one nobody has to choose from a list.
 */

interface Route {
  id: string;
  label: string;
  /** The one thing someone wants to know before reading the steps. */
  cost: string;
  steps: string[];
  note?: string;
}

const ROUTES: Route[] = [
  {
    id: "screenshot",
    label: "Screenshot",
    cost: "Nothing installed, on any phone, iPhone included",
    steps: [
      "Open this page on the phone you play on.",
      "Start champion select in Wild Rift.",
      "Take a screenshot the way your phone does it. Most Androids: Power and Volume Down together. iPhone: Side button and Volume Up.",
      "Come back to this page, tap the drop box, and pick that screenshot.",
      "The bans and picks appear below. Take another screenshot after their last pick and drop it in again to refresh.",
    ],
    note: "This is the only route that asks you to set up nothing at all, and the only one that works with just a phone.",
  },
  {
    id: "phone-link",
    label: "Windows + Android",
    cost: "Nothing to download on Windows 11 or on most Samsung phones",
    steps: [
      "On the PC, open Phone Link. It comes with Windows 11; search the Start menu for it.",
      "On the phone, open Link to Windows. It is built into Samsung, Honor and Surface Duo phones; on others, install it from the Play Store.",
      "Scan the code Phone Link shows and finish pairing.",
      "In Phone Link, open Phone screen so the phone is mirrored in a window.",
      "Start champion select, then press Read a live mirror below and share the Phone Link window.",
    ],
    note: "Mirroring the whole phone screen is offered on select Samsung, Honor and Surface Duo models. If yours is not one, use scrcpy or the screenshot route.",
  },
  {
    id: "scrcpy",
    label: "Any Android, by cable",
    cost: "A free program on the PC, nothing on the phone",
    steps: [
      "On the phone: Settings, About phone, tap Build number seven times, then Developer options, and turn on USB debugging.",
      "Plug the phone into the PC and accept the debugging prompt on the phone.",
      "Download scrcpy, which is free and open source, and run it. The phone screen opens in a window with almost no delay.",
      "Start champion select, then press Read a live mirror below and share the scrcpy window.",
    ],
    note: "Works on Windows, macOS and Linux, and on any Android phone regardless of brand.",
  },
  {
    id: "airplay",
    label: "Windows + iPhone",
    cost: "An AirPlay receiver on the PC, nothing on the phone",
    steps: [
      "Install an AirPlay receiver on the PC. Windows cannot receive AirPlay on its own; the Microsoft Store has free receivers, and Reflector and AirServer are the paid ones.",
      "Put the PC and the iPhone on the same Wi-Fi network.",
      "On the iPhone, open Control Centre, tap Screen Mirroring, and pick the PC.",
      "Start champion select, then press Read a live mirror below and share the receiver's window.",
    ],
  },
  {
    id: "quicktime",
    label: "Mac + iPhone",
    cost: "Nothing installed, it is built into macOS",
    steps: [
      "Plug the iPhone into the Mac, unlock it, and tap Trust.",
      "Open QuickTime Player, then File, then New Movie Recording.",
      "Click the arrow next to the record button and choose the iPhone as the camera.",
      "Start champion select, then press Read a live mirror below and share the QuickTime window.",
    ],
  },
];

/** The route this visitor most likely wants, opened for them. */
function suggest(): string {
  if (typeof navigator === "undefined") return "screenshot";
  const ua = navigator.userAgent;
  if (/Android|iPhone|iPad|iPod/i.test(ua)) return "screenshot";
  const iphone = /iPhone|iPad/i.test(ua);
  if (/Windows/i.test(ua)) return iphone ? "airplay" : "phone-link";
  if (/Mac OS X|Macintosh/i.test(ua)) return "quicktime";
  return "screenshot";
}

export function SecondScreenGuide() {
  const [open, setOpen] = useState("screenshot");
  const [mine, setMine] = useState("");

  // Client-only: the server has no user agent, and guessing on it would render
  // one route on the server and another in the browser.
  useEffect(() => {
    const pick = suggest();
    setMine(pick);
    setOpen(pick);
  }, []);

  const route = ROUTES.find((r) => r.id === open) ?? ROUTES[0];

  return (
    <div className="glass rounded-2xl p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-bold uppercase tracking-wide text-muted">
          Getting your screen here
        </h2>
        <span className="text-[11px] text-faint">
          the phone never installs anything except where it says so
        </span>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {ROUTES.map((r) => (
          <button
            key={r.id}
            onClick={() => setOpen(r.id)}
            className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
              open === r.id ? "bg-accent text-white" : "glass text-muted hover:text-text"
            }`}
          >
            {r.label}
            {mine === r.id && (
              <span className={`ml-1.5 text-[9px] uppercase ${
                open === r.id ? "text-white/70" : "text-accent"
              }`}>
                yours
              </span>
            )}
          </button>
        ))}
      </div>

      <p className="mt-3 text-xs font-semibold text-accent">{route.cost}</p>
      <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-sm text-muted">
        {route.steps.map((step) => <li key={step}>{step}</li>)}
      </ol>
      {route.note && <p className="mt-2 text-xs text-faint">{route.note}</p>}
      {route.id !== "screenshot" && (
        <p className="mt-2 text-xs text-faint">
          When the share picker opens, choose the <strong>mirror window</strong> rather than
          your whole screen. The whole screen works too, but the phone then sits in the
          middle of a desktop and has to be found first.
        </p>
      )}
    </div>
  );
}
