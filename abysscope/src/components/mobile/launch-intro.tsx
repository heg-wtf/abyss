"use client";

import * as React from "react";

/**
 * Full-screen WebGL launch intro for the PWA's very first run.
 *
 * Animation: radial cube burst from center + chromatic aberration +
 * subtle horizontal scan lines. Designed to mirror the reference
 * frame the user picked — bright warm-white core, cold blue/cyan
 * periphery, hard RGB channel split toward the edges.
 *
 * Lifecycle:
 *   - Mounted by ``MobileShell`` only when ``localStorage`` shows the
 *     intro has never been seen (and ``prefers-reduced-motion`` is
 *     not active).
 *   - Calls ``onComplete`` after ``durationMs`` (default 1500 ms) or
 *     immediately on the first user tap.
 *   - Cleans up the GL context + RAF on unmount.
 */

const VERTEX_SHADER = `attribute vec2 a_pos;
void main() {
  gl_Position = vec4(a_pos, 0.0, 1.0);
}
`;

const FRAGMENT_SHADER = `precision highp float;
uniform float u_time;       // seconds since mount
uniform float u_duration;   // total animation duration (seconds)
uniform vec2  u_resolution;

float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

// Voronoi-style cells that give the "cubic debris" look.
float cells(vec2 uv, float scale) {
  uv *= scale;
  vec2 i = floor(uv);
  vec2 f = fract(uv);
  float minDist = 1.0;
  for (int y = -1; y <= 1; y++) {
    for (int x = -1; x <= 1; x++) {
      vec2 g = vec2(float(x), float(y));
      vec2 p = g + vec2(hash(i + g), hash(i + g + 7.31)) * 0.95;
      float d = length(p - f);
      minDist = min(minDist, d);
    }
  }
  return minDist;
}

// Sample the burst pattern at uv. Pulls separately for each RGB
// channel so we can fake chromatic aberration without sampling a
// real texture.
vec3 burst(vec2 uv, float t) {
  vec2 c = uv - 0.5;
  float dist = length(c);

  // Radial zoom — debris streaks outward as time grows.
  float zoom = 1.0 + t * 6.0;
  vec2 sampleUv = 0.5 + c / zoom;

  // Cubic debris layer.
  float v1 = cells(sampleUv + vec2(0.0, t * 0.2), 22.0);
  float v2 = cells(sampleUv * 1.3 + vec2(t * 0.1, 0.0), 35.0);
  float cubes = smoothstep(0.42, 0.0, v1) + smoothstep(0.30, 0.0, v2) * 0.5;

  // Cold blue/cyan tone for the debris.
  vec3 col = cubes * vec3(0.35, 0.55, 0.95);

  // Warm gaussian core. Bright early, fades out by t = 1.0.
  float coreIntensity = mix(3.2, 0.25, smoothstep(0.0, 1.0, t));
  float core = exp(-dist * dist * 22.0) * coreIntensity;
  col += core * vec3(1.0, 0.9, 0.55);

  // Faint horizontal scan lines on top.
  float scan = 0.92 + 0.08 * sin(uv.y * u_resolution.y * 0.5);
  col *= scan;

  return col;
}

void main() {
  vec2 uv = gl_FragCoord.xy / u_resolution;
  vec2 c = uv - 0.5;
  float dist = length(c);
  float t = u_time;

  // Radial chromatic aberration — stronger at the edges.
  float ab = 0.006 + 0.025 * dist;
  vec3 rgb;
  rgb.r = burst(uv + c * ab, t).r;
  rgb.g = burst(uv, t).g;
  rgb.b = burst(uv - c * ab, t).b;

  // Fade out the last 0.3 s so the handoff to the chat UI is smooth.
  float fade = 1.0 - smoothstep(u_duration - 0.3, u_duration, t);
  rgb *= fade;

  gl_FragColor = vec4(rgb, fade);
}
`;

interface LaunchIntroProps {
  /**
   * Total intro duration in milliseconds. The animation fades out
   * over the final ~300 ms and ``onComplete`` fires when the clock
   * crosses this threshold.
   */
  durationMs?: number;
  /** Called once when the intro finishes (timeout, tap, or fallback). */
  onComplete: () => void;
}

export function LaunchIntro({
  durationMs = 1500,
  onComplete,
}: LaunchIntroProps) {
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);
  const completedRef = React.useRef(false);

  const complete = React.useCallback(() => {
    if (completedRef.current) return;
    completedRef.current = true;
    onComplete();
  }, [onComplete]);

  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // Honor reduced-motion preference — skip the animation entirely
    // but still flip the "seen" flag so we don't re-enter on every
    // launch.
    if (
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      const id = window.setTimeout(complete, 60);
      return () => window.clearTimeout(id);
    }

    const gl =
      (canvas.getContext("webgl", {
        alpha: true,
        antialias: false,
        premultipliedAlpha: false,
      }) as WebGLRenderingContext | null) ??
      (canvas.getContext("experimental-webgl") as WebGLRenderingContext | null);
    if (!gl) {
      // No WebGL — bail to whatever's behind us.
      complete();
      return;
    }

    const program = _buildProgram(gl, VERTEX_SHADER, FRAGMENT_SHADER);
    if (!program) {
      complete();
      return;
    }

    // Full-screen quad (two triangles).
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]),
      gl.STATIC_DRAW,
    );

    const aPos = gl.getAttribLocation(program, "a_pos");
    const uTime = gl.getUniformLocation(program, "u_time");
    const uDuration = gl.getUniformLocation(program, "u_duration");
    const uRes = gl.getUniformLocation(program, "u_resolution");

    gl.useProgram(program);
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const resize = () => {
      const width = Math.floor(canvas.clientWidth * dpr);
      const height = Math.floor(canvas.clientHeight * dpr);
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform2f(uRes, canvas.width, canvas.height);
    };
    resize();
    window.addEventListener("resize", resize);

    gl.uniform1f(uDuration, durationMs / 1000);

    const start = performance.now();
    let frameId = 0;

    const tick = (now: number) => {
      const elapsedSeconds = (now - start) / 1000;
      gl.uniform1f(uTime, elapsedSeconds);
      gl.clearColor(0, 0, 0, 1);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.drawArrays(gl.TRIANGLES, 0, 6);

      if (now - start < durationMs) {
        frameId = requestAnimationFrame(tick);
      } else {
        complete();
      }
    };
    frameId = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(frameId);
      window.removeEventListener("resize", resize);
      // Best-effort GL cleanup — losing the context drops every
      // attached resource (program, shaders, buffer) in one call.
      const loseExt = gl.getExtension("WEBGL_lose_context");
      if (loseExt) loseExt.loseContext();
    };
  }, [complete, durationMs]);

  return (
    <div
      className="fixed inset-0 z-[100] bg-black"
      role="presentation"
      aria-hidden
      onClick={complete}
      onTouchStart={complete}
    >
      <canvas ref={canvasRef} className="block h-full w-full" />
    </div>
  );
}

function _buildProgram(
  gl: WebGLRenderingContext,
  vertexSource: string,
  fragmentSource: string,
): WebGLProgram | null {
  const vertex = _compile(gl, gl.VERTEX_SHADER, vertexSource);
  const fragment = _compile(gl, gl.FRAGMENT_SHADER, fragmentSource);
  if (!vertex || !fragment) return null;

  const program = gl.createProgram();
  if (!program) return null;
  gl.attachShader(program, vertex);
  gl.attachShader(program, fragment);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    gl.deleteProgram(program);
    return null;
  }
  return program;
}

function _compile(
  gl: WebGLRenderingContext,
  type: number,
  source: string,
): WebGLShader | null {
  const shader = gl.createShader(type);
  if (!shader) return null;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}
