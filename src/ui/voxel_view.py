from __future__ import annotations
import json
from pathlib import Path

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, QUrl

_THREEJS_LOCAL = Path(__file__).parent.parent.parent / "assets" / "js" / "three.min.js"
if _THREEJS_LOCAL.exists():
    _THREEJS_SRC = _THREEJS_LOCAL.as_uri()
else:
    _THREEJS_SRC = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#040a10; overflow:hidden; }
  canvas

    position:fixed; inset:0; display:flex; flex-direction:column;
    align-items:center; justify-content:center;
    background:
    text-align:center; gap:10px;
    font-family: Helvetica Neue, sans-serif;
    z-index:10;
  }

    display:none; position:fixed; top:10px; left:10px; z-index:5;
    background:rgba(4,10,16,0.90); border:1px solid
    border-radius:3px; padding:8px 13px;
    color:
    pointer-events:none;
    font-family: Menlo, Consolas, monospace;
    min-width: 150px;
  }

    display:none; position:fixed; top:50%; left:50%;
    transform:translate(-50%,-50%); pointer-events:none; z-index:5;
  }

    display:none; position:fixed; bottom:10px; left:50%;
    transform:translateX(-50%); z-index:5;
    background:rgba(4,10,16,0.85); border:1px solid
    border-radius:3px; padding:5px 16px;
    color:
    pointer-events:none; font-family: Helvetica Neue, sans-serif;
    white-space:nowrap;
  }

    display:none; position:fixed; top:10px; right:10px; z-index:5;
    pointer-events:none;
  }
</style>
</head>
<body>

<div id="placeholder">
  <div class="icon"></div>
  <div class="title">Click a station on the map</div>
  <div>to explore the cave passage</div>
</div>

<canvas id="gl"></canvas>

<div id="hud">
  <div class="sname" id="h-name">--</div>
  <div class="row"><span class="lbl">Depth</span><span class="val" id="h-depth">--</span></div>
  <div class="row"><span class="lbl">Width</span><span class="val" id="h-width">--</span></div>
  <div class="row"><span class="lbl">Height</span><span class="val" id="h-height">--</span></div>
  <div class="row"><span class="lbl">Bearing</span><span class="val" id="h-bearing">--</span></div>
</div>

<div id="crosshair">
  <svg width="20" height="20" viewBox="0 0 20 20">
    <line x1="10" y1="3" x2="10" y2="8" stroke="rgba(255,255,255,0.6)" stroke-width="1.5"/>
    <line x1="10" y1="12" x2="10" y2="17" stroke="rgba(255,255,255,0.6)" stroke-width="1.5"/>
    <line x1="3" y1="10" x2="8" y2="10" stroke="rgba(255,255,255,0.6)" stroke-width="1.5"/>
    <line x1="12" y1="10" x2="17" y2="10" stroke="rgba(255,255,255,0.6)" stroke-width="1.5"/>
  </svg>
</div>

<div id="controls">WASD -- move &nbsp;&
<div id="compass-wrap"><canvas id="compass" width="52" height="52"></canvas></div>
<button id="close-btn" onclick="clearView()" style="display:none;position:fixed;top:10px;left:50%;transform:translateX(-50%);z-index:10;background:rgba(4,10,16,0.88);border:1px solid #182430;border-radius:3px;color:#6B7A8A;font-size:10px;padding:4px 14px;cursor:pointer;font-family:Helvetica Neue,sans-serif;letter-spacing:0.05em;">&

<script src="{THREEJS_SRC}"></script>
<script>
const BLOCKS = {
  1:{shades:[0.80,0.70,1.00,0.55,0.85,0.75],colors:[0x787878,0x727272,0x7E7E7E,0x6C6C6C,0x747474,0x6E6E6E],opacity:1,solid:true},
  2:{shades:[0.80,0.70,1.00,0.55,0.85,0.75],colors:[0x8B7355,0x856F50,0x917959,0x7D674C,0x897153,0x836C4E],opacity:1,solid:true},
  3:{shades:[1,1,1,1,1,1],colors:[0x1B5080,0x1B5080,0x2060A0,0x163C60,0x1B5080,0x1B5080],opacity:0.42,solid:false},
  4:{shades:[0.85,0.75,1.00,0.60,0.90,0.80],colors:[0xC8A96E,0xC2A368,0xCEAF74,0xBA9B62,0xC6A76C,0xC0A166],opacity:1,solid:true},
  5:{shades:[0.80,0.70,1.00,0.55,0.85,0.75],colors:[0x3C3C44,0x36363E,0x42424A,0x303038,0x3A3A42,0x34343C],opacity:1,solid:true},
};
const FNORM=[[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]];
function fverts(px,py,pz,f){
  switch(f){
    case 0:return[[px+1,py,pz],[px+1,py+1,pz],[px+1,py+1,pz+1],[px+1,py,pz+1]];
    case 1:return[[px,py,pz+1],[px,py+1,pz+1],[px,py+1,pz],[px,py,pz]];
    case 2:return[[px,py+1,pz],[px,py+1,pz+1],[px+1,py+1,pz+1],[px+1,py+1,pz]];
    case 3:return[[px,py,pz+1],[px,py,pz],[px+1,py,pz],[px+1,py,pz+1]];
    case 4:return[[px+1,py,pz+1],[px+1,py+1,pz+1],[px,py+1,pz+1],[px,py,pz+1]];
    case 5:return[[px,py,pz],[px,py+1,pz],[px+1,py+1,pz],[px+1,py,pz]];
  }
}

let scene,camera,renderer,animId;
let meshes=[],bubbles=[];
let isDragging=false,lastMX=0,lastMY=0;
const keys={};
const euler=new THREE.Euler(0,0,0,'YXZ');

function initScene(){
  if(animId) cancelAnimationFrame(animId);
  if(scene){
    meshes.forEach(m=>{m.geometry.dispose();m.material.dispose();});
    bubbles.forEach(b=>{b.geometry.dispose();b.material.dispose();});
    meshes=[];bubbles=[];
  }
  scene=new THREE.Scene();
  scene.fog=new THREE.FogExp2(0x040A10,0.05);
  scene.background=new THREE.Color(0x040A10);
  camera=new THREE.PerspectiveCamera(70,innerWidth/innerHeight,0.1,60);
  scene.add(camera);
  const torch=new THREE.PointLight(0xC8E8FF,4.0,14,2);
  camera.add(torch);
  scene.add(new THREE.AmbientLight(0x061420,1.5));
  const fg=new THREE.PointLight(0x204060,0.6,10);
  fg.position.set(0,-4,0); scene.add(fg);
  if(!renderer){
    const cv=document.getElementById('gl');
    renderer=new THREE.WebGLRenderer({canvas:cv,antialias:true});
    renderer.setPixelRatio(Math.min(devicePixelRatio,2));
    cv.addEventListener('mousedown',e=>{isDragging=true;lastMX=e.clientX;lastMY=e.clientY;cv.style.cursor='grabbing';});
    document.addEventListener('mouseup',()=>{isDragging=false;document.getElementById('gl').style.cursor='crosshair';});
    document.addEventListener('mousemove',e=>{
      if(!isDragging)return;
      euler.setFromQuaternion(camera.quaternion);
      euler.y-=(e.clientX-lastMX)*0.0045;
      euler.x-=(e.clientY-lastMY)*0.0045;
      euler.x=Math.max(-Math.PI/2,Math.min(Math.PI/2,euler.x));
      camera.quaternion.setFromEuler(euler);
      lastMX=e.clientX;lastMY=e.clientY;
    });
    document.addEventListener('keydown',e=>{keys[e.code]=true;});
    document.addEventListener('keyup',e=>delete keys[e.code]);
    window.addEventListener('resize',()=>{if(!camera||!renderer)return;camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight);});
    cv.style.cursor='crosshair';
  }
  renderer.setSize(innerWidth,innerHeight);
}

function buildMeshes(voxels,N){
  const half=N/2;
  function get(x,y,z){if(x<0||x>=N||y<0||y>=N||z<0||z>=N)return 1;return voxels[z*N*N+y*N+x];}
  const buckets={};
  for(let z=0;z<N;z++) for(let y=0;y<N;y++) for(let x=0;x<N;x++){
    const bid=get(x,y,z);
    if(!bid||!BLOCKS[bid])continue;
    const bd=BLOCKS[bid];
    for(let f=0;f<6;f++){
      const[nx,ny,nz]=FNORM[f];
      const nb=get(x+nx,y+ny,z+nz);
      const show=nb===0||(nb===3&&bd.solid)||(!bd.solid&&nb===0);
      if(!show)continue;
      const key=bid+'_'+f;
      if(!buckets[key])buckets[key]={bid,face:f,pos:[],idx:[],norm:[],bv:0};
      const g=buckets[key];
      const vs=fverts(x-half,y-half,z-half,f);
      const bv=g.bv;
      for(const v of vs){g.pos.push(v[0],v[1],v[2]);g.norm.push(nx,ny,nz);}
      g.idx.push(bv,bv+1,bv+2,bv,bv+2,bv+3);
      g.bv+=4;
    }
  }
  Object.values(buckets).forEach(g=>{
    if(!g.pos.length)return;
    const def=BLOCKS[g.bid];
    const shade=def.shades[g.face];
    const bc=def.colors[g.face];
    const r=((bc>>16)&0xff)/255*shade;
    const gv=((bc>>8)&0xff)/255*shade;
    const b=(bc&0xff)/255*shade;
    const geo=new THREE.BufferGeometry();
    geo.setAttribute('position',new THREE.Float32BufferAttribute(g.pos,3));
    geo.setAttribute('normal',new THREE.Float32BufferAttribute(g.norm,3));
    geo.setIndex(g.idx);
    geo.computeBoundingSphere();
    const mat=new THREE.MeshLambertMaterial({
      color:new THREE.Color(r,gv,b),
      transparent:def.opacity<1,opacity:def.opacity,
      emissive:g.bid===3?new THREE.Color(0x030F1E):new THREE.Color(0),
      emissiveIntensity:g.bid===3?0.6:0,
      side:g.bid===3?THREE.DoubleSide:THREE.FrontSide,
      depthWrite:def.opacity>=1,
    });
    const mesh=new THREE.Mesh(geo,mat);
    scene.add(mesh);meshes.push(mesh);
  });
}

function addBubbles(N){
  const geo=new THREE.SphereGeometry(0.07,5,5);
  const mat=new THREE.MeshBasicMaterial({color:0x88CCFF,transparent:true,opacity:0.28});
  for(let i=0;i<50;i++){
    const m=new THREE.Mesh(geo,mat.clone());
    m.position.set((Math.random()-0.5)*N*0.4,(Math.random()-0.5)*N*0.25,(Math.random()-0.5)*N*0.4);
    m.userData.vy=0.01+Math.random()*0.02;
    m.userData.wobble=Math.random()*Math.PI*2;
    m.userData.range=N*0.13;
    scene.add(m);bubbles.push(m);
  }
}

function drawCompass(bearing){
  const c=document.getElementById('compass');
  const ctx=c.getContext('2d');
  const cx=26,cy=26,r=21;
  ctx.clearRect(0,0,52,52);
  ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);
  ctx.fillStyle='rgba(4,10,16,0.88)';ctx.fill();
  ctx.strokeStyle='#1E3040';ctx.lineWidth=1;ctx.stroke();
  const a=bearing*Math.PI/180-Math.PI/2;
  ctx.save();ctx.translate(cx,cy);ctx.rotate(a);
  ctx.beginPath();ctx.moveTo(0,-r+4);ctx.lineTo(4,2);ctx.lineTo(-4,2);ctx.closePath();
  ctx.fillStyle='#D03030';ctx.fill();
  ctx.beginPath();ctx.moveTo(0,r-4);ctx.lineTo(4,-2);ctx.lineTo(-4,-2);ctx.closePath();
  ctx.fillStyle='#3A4A5A';ctx.fill();
  ctx.restore();
  ctx.fillStyle='#6B7A8A';ctx.font='bold 8px Helvetica';
  ctx.textAlign='center';ctx.textBaseline='middle';
  ctx.fillText('N',cx,cy-r+8);
}

function placeCamera(bearing,camY){
  camera.position.set(0,camY||0,0);
  euler.y=-THREE.MathUtils.degToRad(bearing);
  euler.x=0;
  camera.quaternion.setFromEuler(euler);
}

function animate(){
  animId=requestAnimationFrame(animate);
  const spd=0.06;
  const dir=new THREE.Vector3();
  if(keys['KeyW']||keys['ArrowUp'])dir.z-=1;
  if(keys['KeyS']||keys['ArrowDown'])dir.z+=1;
  if(keys['KeyA']||keys['ArrowLeft'])dir.x-=1;
  if(keys['KeyD']||keys['ArrowRight'])dir.x+=1;
  if(keys['Space'])dir.y+=1;
  if(keys['ShiftLeft'])dir.y-=1;
  if(dir.lengthSq()>0){dir.normalize().multiplyScalar(spd);dir.applyQuaternion(camera.quaternion);camera.position.add(dir);}
  const t=performance.now()*0.001;
  bubbles.forEach(b=>{
    b.position.y+=b.userData.vy;
    b.position.x+=Math.sin(t+b.userData.wobble)*0.003;
    if(b.position.y>b.userData.range)b.position.y=-b.userData.range;
  });
  renderer.render(scene,camera);
}

function loadChunk(jsonStr){
  const data = JSON.parse(jsonStr);
  document.getElementById('h-name').textContent=data.station;
  document.getElementById('h-depth').textContent=data.depth_m.toFixed(1)+' m';
  document.getElementById('h-width').textContent=(data.lrud.l+data.lrud.r).toFixed(1)+' m';
  document.getElementById('h-height').textContent=(data.lrud.u+data.lrud.d).toFixed(1)+' m';
  document.getElementById('h-bearing').textContent=data.passage_bearing.toFixed(0)+'deg';
  document.getElementById('placeholder').style.display='none';
  document.getElementById('hud').style.display='block';
  document.getElementById('crosshair').style.display='block';
  document.getElementById('controls').style.display='block';
  document.getElementById('compass-wrap').style.display='block';
  document.getElementById('close-btn').style.display='block';
  drawCompass(data.passage_bearing);
  initScene();
  buildMeshes(data.voxels,data.chunk_size);
  addBubbles(data.chunk_size);
  placeCamera(data.passage_bearing,data.cam_y_offset||0);
  animate();
}

function clearView(){
  if(animId)cancelAnimationFrame(animId);
  document.getElementById('placeholder').style.display='flex';
  ['hud','crosshair','controls','compass-wrap','close-btn'].forEach(id=>document.getElementById(id).style.display='none');
  if(scene){
    meshes.forEach(m=>{m.geometry.dispose();m.material.dispose();scene.remove(m);});
    bubbles.forEach(b=>{b.geometry.dispose();b.material.dispose();scene.remove(b);});
    meshes=[];bubbles=[];
  }
}
</script>
</body>
</html>"""


class VoxelViewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings
            self._web = QWebEngineView()
            self._web.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            self._web.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            html = _HTML_TEMPLATE.replace("{THREEJS_SRC}", _THREEJS_SRC)
            base_url = QUrl(_THREEJS_LOCAL.parent.as_uri() + "/") if _THREEJS_LOCAL.exists() else QUrl("about:blank")
            self._web.setHtml(html, base_url)
            layout.addWidget(self._web)
            self._available = True
        except ImportError:
            fallback = QLabel("PyQt6-WebEngine not installed.\n\nRun: pip install PyQt6-WebEngine")
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback.setStyleSheet("background:#040a10; color:#6B7A8A; font-size:12px;")
            layout.addWidget(fallback)
            self._available = False

    def load_station(self, chunk_data: dict) -> None:
        if not self._available:
            return
        json_str = json.dumps(chunk_data)
        safe = json_str.replace("\\", "\\\\").replace("`", "\\`")
        self._web.page().runJavaScript(f"loadChunk(`{safe}`);")

    def clear(self) -> None:
        if not self._available:
            return
        self._web.page().runJavaScript("clearView();")
