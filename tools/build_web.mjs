import fs from 'node:fs/promises';
import vm from 'node:vm';
import path from 'node:path';
const files=await fs.readdir('frontend/web');
await fs.mkdir('dist/web',{recursive:true});
for(const name of files){
 const content=await fs.readFile(path.join('frontend/web',name),'utf8');
 if(name.endsWith('.js'))new vm.Script(content,{filename:name});
 await fs.writeFile(path.join('dist/web',name),content);
}
const html=await fs.readFile('frontend/source/睡眠日誌表單.html','utf8');
if(html.includes('id="f-sleep-time-ampm"')||html.includes('type="time"'))throw Error('Ambiguous time control detected');
await fs.writeFile('dist/index.html',html);
console.log(`Built diary + ${files.length} web assets; runtime /api/config is served by Flask.`);

await fs.cp('frontend/line','dist/line',{recursive:true});
