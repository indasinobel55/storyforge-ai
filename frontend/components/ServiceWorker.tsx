const basePath = process.env.NEXT_BASE_PATH || "";

export default function ServiceWorker() {
  const swPath = basePath ? `${basePath}/sw.js` : "/sw.js";
  return (
    <script
      dangerouslySetInnerHTML={{
        __html: `if ("serviceWorker" in navigator) { window.addEventListener("load", function () { navigator.serviceWorker.register("${swPath}").catch(function () {}); }); }`,
      }}
    />
  );
}
