import postgres from 'npm:postgres@3.4.7';
import {CloudStore} from './store.mjs';
import {createGateway,LineTransport} from './gateway.mjs';

declare const EdgeRuntime:{waitUntil(promise:Promise<unknown>):void};
type Query={query(text:string,params?:postgres.ParameterOrJSON<never>[]):Promise<{rows:postgres.Row[]}>};
type Work=(query:Query)=>Promise<unknown>;

const databaseURL=Deno.env.get('NSYSU_LINE_DATABASE_URL')||Deno.env.get('SUPABASE_DB_URL');
const token=Deno.env.get('NSYSU_LINE_CHANNEL_ACCESS_TOKEN');
const secret=Deno.env.get('NSYSU_LINE_CHANNEL_SECRET');
const bindingURL=Deno.env.get('NSYSU_LINE_BINDING_URL');
if(!databaseURL||!token||!secret||!bindingURL)throw new Error('Private LINE cloud settings required');
const connection=postgres(databaseURL,{max:4,prepare:false,idle_timeout:10,connect_timeout:10,ssl:'require'});
const database={transaction:(work:Work)=>connection.begin(sql=>work({query:async(text,params=[])=>({rows:Array.from(await sql.unsafe(text,params))})}))};
const store=new CloudStore(database);
const gateway=createGateway({store,line:new LineTransport(token),secret,bindingURL,waitUntil:(promise:Promise<unknown>)=>EdgeRuntime.waitUntil(promise)});
Deno.serve(gateway);
