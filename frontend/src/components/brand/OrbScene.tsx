"use client";

import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";

import type { OrbState } from "./orb-state";

/**
 * The Living Orb's 3D scene. Dynamically imported (ssr:false) by <LivingOrb>.
 * Single canvas, unlit emissive shader (no postprocessing) + a CSS glow behind
 * it for the ambient halo — cheap and elegant. State modulates motion only.
 */

const vertexShader = /* glsl */ `
  uniform float u_time;
  uniform float u_amp;
  uniform float u_speed;
  varying vec3 v_normal;
  varying vec3 v_view;
  varying float v_disp;

  // Classic Ashima simplex noise (3D).
  vec4 permute(vec4 x){return mod(((x*34.0)+1.0)*x,289.0);}
  vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
  float snoise(vec3 v){
    const vec2 C=vec2(1.0/6.0,1.0/3.0);
    const vec4 D=vec4(0.0,0.5,1.0,2.0);
    vec3 i=floor(v+dot(v,C.yyy));
    vec3 x0=v-i+dot(i,C.xxx);
    vec3 g=step(x0.yzx,x0.xyz);
    vec3 l=1.0-g;
    vec3 i1=min(g.xyz,l.zxy);
    vec3 i2=max(g.xyz,l.zxy);
    vec3 x1=x0-i1+1.0*C.xxx;
    vec3 x2=x0-i2+2.0*C.xxx;
    vec3 x3=x0-1.0+3.0*C.xxx;
    i=mod(i,289.0);
    vec4 p=permute(permute(permute(
      i.z+vec4(0.0,i1.z,i2.z,1.0))
      +i.y+vec4(0.0,i1.y,i2.y,1.0))
      +i.x+vec4(0.0,i1.x,i2.x,1.0));
    float n_=1.0/7.0;
    vec3 ns=n_*D.wyz-D.xzx;
    vec4 j=p-49.0*floor(p*ns.z*ns.z);
    vec4 x_=floor(j*ns.z);
    vec4 y_=floor(j-7.0*x_);
    vec4 x=x_*ns.x+ns.yyyy;
    vec4 y=y_*ns.x+ns.yyyy;
    vec4 h=1.0-abs(x)-abs(y);
    vec4 b0=vec4(x.xy,y.xy);
    vec4 b1=vec4(x.zw,y.zw);
    vec4 s0=floor(b0)*2.0+1.0;
    vec4 s1=floor(b1)*2.0+1.0;
    vec4 sh=-step(h,vec4(0.0));
    vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;
    vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
    vec3 p0=vec3(a0.xy,h.x);
    vec3 p1=vec3(a0.zw,h.y);
    vec3 p2=vec3(a1.xy,h.z);
    vec3 p3=vec3(a1.zw,h.w);
    vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
    p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
    vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0);
    m=m*m;
    return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
  }

  void main(){
    float t = u_time * u_speed;
    float n = snoise(normal * 1.6 + t);
    float disp = n * u_amp;
    v_disp = disp;
    vec3 pos = position + normal * disp;
    v_normal = normalize(normalMatrix * normal);
    vec4 mv = modelViewMatrix * vec4(pos, 1.0);
    v_view = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
  }
`;

const fragmentShader = /* glsl */ `
  uniform vec3 u_colorA;
  uniform vec3 u_colorB;
  uniform float u_intensity;
  varying vec3 v_normal;
  varying vec3 v_view;
  varying float v_disp;

  void main(){
    float fres = pow(1.0 - max(dot(normalize(v_normal), normalize(v_view)), 0.0), 2.4);
    vec3 base = mix(u_colorA, u_colorB, clamp(v_disp * 2.5 + 0.4, 0.0, 1.0));
    vec3 color = base + u_colorB * fres * u_intensity;
    float alpha = clamp(0.55 + fres * 0.9, 0.0, 1.0);
    gl_FragColor = vec4(color, alpha);
  }
`;

const STATE_TARGET: Record<
  OrbState,
  { amp: number; speed: number; intensity: number }
> = {
  idle: { amp: 0.12, speed: 0.35, intensity: 1.1 },
  thinking: { amp: 0.26, speed: 1.2, intensity: 1.8 },
  listening: { amp: 0.18, speed: 0.7, intensity: 1.45 },
  update: { amp: 0.17, speed: 0.6, intensity: 1.7 },
  // Future extension points (reserved; not yet triggered by real events).
  "agent-working": { amp: 0.24, speed: 1.05, intensity: 1.7 },
  "approval-needed": { amp: 0.2, speed: 0.5, intensity: 1.95 },
  "workflow-learning": { amp: 0.22, speed: 0.9, intensity: 1.6 },
};

function OrbMesh({ state }: { state: OrbState }) {
  const matRef = useRef<THREE.ShaderMaterial>(null);
  const meshRef = useRef<THREE.Mesh>(null);

  const uniforms = useMemo(
    () => ({
      u_time: { value: 0 },
      u_amp: { value: STATE_TARGET.idle.amp },
      u_speed: { value: STATE_TARGET.idle.speed },
      u_intensity: { value: STATE_TARGET.idle.intensity },
      u_colorA: { value: new THREE.Color("#16c98a") },
      u_colorB: { value: new THREE.Color("#7cffc4") },
    }),
    [],
  );

  useFrame((_, delta) => {
    const mat = matRef.current;
    const mesh = meshRef.current;
    if (!mat || !mesh) return;
    mat.uniforms.u_time.value += delta;
    const target = STATE_TARGET[state];
    const k = 1 - Math.pow(0.001, delta); // frame-rate independent lerp
    mat.uniforms.u_amp.value += (target.amp - mat.uniforms.u_amp.value) * k;
    mat.uniforms.u_speed.value +=
      (target.speed - mat.uniforms.u_speed.value) * k;
    mat.uniforms.u_intensity.value +=
      (target.intensity - mat.uniforms.u_intensity.value) * k;
    mesh.rotation.y += delta * 0.12;
    mesh.rotation.x += delta * 0.04;
  });

  return (
    <mesh ref={meshRef}>
      <icosahedronGeometry args={[1, 12]} />
      <shaderMaterial
        ref={matRef}
        uniforms={uniforms}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        transparent
        depthWrite={false}
      />
    </mesh>
  );
}

export default function OrbScene({ state }: { state: OrbState }) {
  return (
    <Canvas
      camera={{ position: [0, 0, 2.7], fov: 45 }}
      dpr={[1, 1.5]}
      gl={{ alpha: true, antialias: true }}
      style={{ background: "transparent" }}
    >
      <OrbMesh state={state} />
    </Canvas>
  );
}
