/// <reference types="vite/client" />

declare module "*.json?url&no-inline" {
  const assetUrl: string;
  export default assetUrl;
}
