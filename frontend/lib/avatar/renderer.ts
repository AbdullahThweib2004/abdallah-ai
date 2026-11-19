/**
 * WebGL drawn by the CPU (no GPU acceleration: blocklisted drivers, some VMs and remote
 * desktops, headless browsers) renders the robot at a few frames per second and blocks the
 * main thread for many seconds. Such browsers report a software rasterizer as the renderer;
 * they get the lightweight CSS orb instead, as without WebGL.
 */
const SOFTWARE_RENDERERS = /swiftshader|llvmpipe|softpipe|software|basic render driver|mesa offscreen/i;

export function isSoftwareRenderer(renderer: string | null | undefined): boolean {
  return Boolean(renderer && SOFTWARE_RENDERERS.test(renderer));
}
