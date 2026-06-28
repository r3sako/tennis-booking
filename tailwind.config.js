/** Tailwind build config — produces a small static/tailwind.css with only the
 *  utility classes actually used in the templates and app.js.
 *  Rebuild after changing classes:
 *    npx tailwindcss@3.4.17 -i ./tailwind.input.css -o ./static/tailwind.css --minify
 */
module.exports = {
  content: ["./templates/**/*.html", "./static/app.js"],
  // Classes assembled dynamically in app.js — kept explicitly just in case.
  safelist: [
    "bg-emerald-600", "bg-rose-600",
    "border-blue-300", "bg-blue-50", "text-blue-600", "bg-blue-500", "hover:bg-blue-600",
    "border-rose-200", "bg-rose-50", "text-rose-700", "text-rose-400", "text-rose-500",
    "border-slate-200", "bg-slate-100", "text-slate-400",
    "border-emerald-200", "bg-emerald-50", "text-emerald-700", "cursor-not-allowed",
    "border-emerald-300", "hover:bg-emerald-100",
  ],
  theme: { extend: {} },
  plugins: [],
};
