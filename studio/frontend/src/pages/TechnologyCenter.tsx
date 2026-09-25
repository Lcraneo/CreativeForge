import { Card } from "../components/ui";

const items = [
 {name:"PReCon",desc:"Pixel Reconstruction Engine\n自研像素重建技术"},
 {name:"FAlign",desc:"Frame Alignment Engine\n切帧对齐技术"},
 {name:"GImport",desc:"Game Engine Import\n引擎一键导入能力"}
];
export default function TechnologyCenter(){
 return <div className="mx-auto max-w-6xl px-8 py-12"><h1 className="text-4xl font-black"><span className="text-sky-400">Creative</span> Engine</h1><p className="mt-3 text-zinc-400">Core technologies behind AI game asset production.</p><div className="mt-10 grid gap-5 md:grid-cols-3">{items.map(i=><Card key={i.name} title={i.name}><p className="whitespace-pre-line text-zinc-300">{i.desc}</p></Card>)}</div></div>
}
