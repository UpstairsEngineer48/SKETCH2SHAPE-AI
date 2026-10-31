import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js';
import Icon from './Icon.jsx';

export default function ModelViewer({ modelUrl, format, isGenerating, statusText }) {
  const mountRef = useRef(null);
  const [loadError, setLoadError] = useState('');
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return undefined;

    setLoadError('');
    setLoaded(false);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#111522');

    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.set(3.7, 2.8, 4.8);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.08;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.065;
    controls.minDistance = 1.5;
    controls.maxDistance = 11;
    controls.target.set(0, 0.1, 0);

    scene.add(new THREE.HemisphereLight(0xe3e8ff, 0x25293a, 2.1));
    const keyLight = new THREE.DirectionalLight(0xffffff, 3.1);
    keyLight.position.set(4, 7, 5);
    keyLight.castShadow = true;
    scene.add(keyLight);
    const rimLight = new THREE.DirectionalLight(0x8c7cff, 2.1);
    rimLight.position.set(-5, 2, -3);
    scene.add(rimLight);

    const grid = new THREE.GridHelper(9, 36, 0x555b78, 0x30364a);
    grid.position.y = -1.25;
    grid.material.opacity = 0.52;
    grid.material.transparent = true;
    scene.add(grid);

    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(5, 64),
      new THREE.MeshStandardMaterial({ color: 0x171b2b, roughness: 0.92, metalness: 0.05, transparent: true, opacity: 0.35 }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -1.255;
    floor.receiveShadow = true;
    scene.add(floor);

    const modelRoot = new THREE.Group();
    scene.add(modelRoot);

    const placeholder = new THREE.Group();
    const wireGeometry = new THREE.EdgesGeometry(new THREE.IcosahedronGeometry(0.92, 1));
    const wire = new THREE.LineSegments(wireGeometry, new THREE.LineBasicMaterial({ color: 0x9d91ff, transparent: true, opacity: 0.9 }));
    placeholder.add(wire);
    const inner = new THREE.Mesh(
      new THREE.IcosahedronGeometry(0.54, 1),
      new THREE.MeshStandardMaterial({ color: 0x6d61bc, roughness: 0.36, metalness: 0.42, transparent: true, opacity: 0.22, wireframe: true }),
    );
    placeholder.add(inner);
    const orbitRing = new THREE.Mesh(
      new THREE.TorusGeometry(1.18, 0.008, 8, 96),
      new THREE.MeshBasicMaterial({ color: 0x4ec9b2, transparent: true, opacity: 0.48 }),
    );
    orbitRing.rotation.x = Math.PI * 0.37;
    placeholder.add(orbitRing);
    placeholder.position.y = 0.08;
    scene.add(placeholder);

    const resize = () => {
      const width = Math.max(mount.clientWidth, 1);
      const height = Math.max(mount.clientHeight, 1);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    };
    resize();
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(mount);

    let disposed = false;
    let loadedObject = null;

    const fitObject = (object) => {
      const bounds = new THREE.Box3().setFromObject(object);
      const size = bounds.getSize(new THREE.Vector3());
      const center = bounds.getCenter(new THREE.Vector3());
      const largestDimension = Math.max(size.x, size.y, size.z) || 1;
      const scale = 2.65 / largestDimension;
      object.scale.setScalar(scale);
      object.position.sub(center.multiplyScalar(scale));
      const fittedBounds = new THREE.Box3().setFromObject(object);
      object.position.y -= fittedBounds.min.y + 0.02;
      object.traverse((child) => {
        if (child.isMesh) {
          child.castShadow = true;
          child.receiveShadow = true;
          if (!child.material || child.material.type === 'MeshBasicMaterial') {
            child.material = new THREE.MeshStandardMaterial({ color: 0xb8b8c8, roughness: 0.55, metalness: 0.14 });
          }
        }
      });
      modelRoot.add(object);
      placeholder.visible = false;
      controls.target.set(0, 0.65, 0);
      controls.update();
      loadedObject = object;
      setLoaded(true);
    };

    if (modelUrl) {
      const loader = format === 'obj' ? new OBJLoader() : new GLTFLoader();
      loader.load(
        modelUrl,
        (result) => {
          if (disposed) return;
          const object = format === 'obj' ? result : result.scene;
          fitObject(object);
        },
        undefined,
        (error) => {
          if (disposed) return;
          console.error('Unable to load generated 3D model:', error);
          setLoadError('The asset URL was returned, but the 3D viewer could not load it. Check that the API serves a valid GLB or OBJ file.');
        },
      );
    }

    let frameId = 0;
    const animate = () => {
      if (disposed) return;
      frameId = requestAnimationFrame(animate);
      if (!modelUrl) {
        placeholder.rotation.y += 0.0028;
        placeholder.rotation.x = Math.sin(performance.now() * 0.00028) * 0.07;
      }
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      disposed = true;
      cancelAnimationFrame(frameId);
      resizeObserver.disconnect();
      controls.dispose();
      scene.traverse((object) => {
        if (object.geometry) object.geometry.dispose();
        if (object.material) {
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.forEach((material) => {
            Object.values(material).forEach((value) => {
              if (value && value.isTexture) value.dispose();
            });
            material.dispose();
          });
        }
      });
      renderer.dispose();
      renderer.domElement.remove();
      if (loadedObject) loadedObject.clear();
    };
  }, [modelUrl, format]);

  return (
    <div className="viewer-shell">
      <div className="viewer-canvas" ref={mountRef} />
      {!modelUrl && !isGenerating && (
        <div className="viewer-empty-state">
          <strong>Your 3D model will appear here</strong>
          <p>Draw or upload a sketch, then start the reconstruction.</p>
        </div>
      )}
      {isGenerating && (
        <div className="viewer-generating-state">
          <div className="generation-spinner"><span /></div>
          <strong>Building your 3D asset</strong>
          <p>{statusText||'Starting · this usually takes a few minutes'}</p>
        </div>
      )}
      {loadError && (
        <div className="viewer-error"><Icon name="alert" size={17} /> <span>{loadError}</span></div>
      )}
      <div className="viewer-overlay-top">
        <span className="scene-label"><span className="scene-label-dot" /> {modelUrl && loaded ? 'MODEL LOADED' : '3D VIEWPORT'}</span>
        <span className="scene-label subtle-label">PERSPECTIVE <span>·</span> ORBIT ENABLED</span>
      </div>
      <div className="viewer-overlay-bottom">
        <span><Icon name="mouse" size={14} /> Drag to orbit</span>
        <span>Scroll to zoom</span>
        <span>Right-drag to pan</span>
      </div>
    </div>
  );
}
