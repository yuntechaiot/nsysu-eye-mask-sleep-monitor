import fs from 'node:fs/promises';
import vm from 'node:vm';
for(const name of await fs.readdir('frontend/web'))if(name.endsWith('.js'))new vm.Script(await fs.readFile('frontend/web/'+name,'utf8'),{filename:name});
console.log('Frontend JavaScript syntax passed');

new vm.Script(await fs.readFile('frontend/line/bind.js','utf8'),{filename:'bind.js'});
for(const name of ['auth_bridge','auth_return'])new vm.Script((await fs.readFile(`frontend/${name}/index.html`,'utf8')).match(/<script>([\s\S]*?)<\/script>/)[1],{filename:name+'.js'});
