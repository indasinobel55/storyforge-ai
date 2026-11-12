export default function ServiceWorker() {
  return (
    <script
      dangerouslySetInnerHTML={{
        __html: `if ("serviceWorker" in navigator) { window.addEventListener("load", function () { navigator.serviceWorker.register("/sw.js").catch(function () {}); }); }`,
      }}
    />
  );
}
