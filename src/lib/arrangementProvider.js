import { DEMO_ARRANGEMENT } from "../data/demoArrangement";

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

// This is the only place the UI asks for song arrangements. Replacing this
// local preview with a licensed catalog or a reviewed-generation pipeline will
// not require rewriting the chart experience.
export async function getPreviewArrangement() {
  await new Promise((resolve) => window.setTimeout(resolve, 650));
  return clone(DEMO_ARRANGEMENT);
}
