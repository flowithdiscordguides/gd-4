/*
 * Screenshot metadata for the GitDesk Guide.
 * Source and packaged rendering choose different bases while reusing the existing project PNGs.
 */
const ASSET_BASE = document.documentElement.dataset.guideAssetBase;
const GUIDE_MEDIA_BASE = document.documentElement.dataset.guideMediaBase;
const START_HERE_MEDIA = [
  { alt: "GitDesk header showing mode and repository controls", src: `${GUIDE_MEDIA_BASE}1)header.png` },
  { alt: "GitDesk toolbar navigation", src: `${GUIDE_MEDIA_BASE}2) toolbar.png` },
  { alt: "GitDesk Settings workspace", src: `${GUIDE_MEDIA_BASE}3) settings.png` },
  { alt: "GitDesk DevTools workspace", src: `${GUIDE_MEDIA_BASE}4) devtools.png` }
];
