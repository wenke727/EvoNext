import { test } from "node:test";
import assert from "node:assert/strict";
import { inspectorFields,filterInspectorFields,safeTraceUrl,traceReferences } from "../src/evidence/inspector.ts";

test("raw inspector preserves zero, null, false, unknown fields and literal source text",()=>{
  const step={index:0,step_id:'900719925474099312345',value:{raw_model_output:'literal \\n <script>synthetic</script>',unknown:false},runtime:null};
  const before=JSON.stringify(step);
  const fields=inspectorFields(step);
  assert.equal(fields[0].json,'0');
  assert.equal(filterInspectorFields(fields,'900719925474099312345')[0].key,'step_id');
  assert.equal(filterInspectorFields(fields,'FALSE')[0].key,'value.unknown');
  assert.equal(filterInspectorFields(fields,'null')[0].key,'runtime');
  assert.equal(filterInspectorFields(fields,'absent').length,0);
  assert.equal(JSON.stringify(step),before);
});

test("trace references stay attached to source positions and never synthesize URLs",()=>{
  const detail={task_id:'synthetic',source_version:0,snapshot_id:'synthetic-snapshot',trajectory:{traj:[
    {index:100,runtime:{trace_ref:{trace_id:'900719925474099312345',observation_id:0,url:'https://example.invalid/trace/synthetic',unknown:true}}},
    {index:999,trace_ref:'synthetic-id-only'},
    {runtime:{trace_ref:{trace_id:9007199254740992,url:'javascript:alert(1)'}}},
  ]}};
  const before=structuredClone(detail);
  const current=traceReferences(detail,0);
  assert.equal(current[0].position,0);
  assert.equal(current[0].traceId,'900719925474099312345');
  assert.equal(current[0].observationId,'0');
  assert.equal(current[0].source,'traj[0].runtime.trace_ref');
  assert.equal(traceReferences(detail,1)[0].url,null);
  assert.equal(traceReferences(detail,2)[0].traceId,null);
  assert.equal(traceReferences(detail,2)[0].url,null);
  assert.equal(traceReferences(detail,null).length,3);
  assert.deepEqual(detail,before);
});

test("missing trace references remain missing and unsafe targets never become links",()=>{
  assert.deepEqual(traceReferences({trajectory:{traj:[{value:{trace_id:'not-a-supported-ref'}}]}},null),[]);
  for(const url of ['javascript:alert(1)','data:text/html,synthetic','/derived/from/task','file:///tmp/synthetic','https://user:secret@example.invalid/']) assert.equal(safeTraceUrl(url),null);
  assert.equal(safeTraceUrl('https://example.invalid/trace/synthetic'),'https://example.invalid/trace/synthetic');
});
