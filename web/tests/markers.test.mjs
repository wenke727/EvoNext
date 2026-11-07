import { test } from "node:test";
import assert from "node:assert/strict";
import { projectStep } from "../src/evidence/projection.ts";
import { bboxGeometry, actionMarkers } from "../src/evidence/markers.ts";

test("BBox object and corner arrays use explicit 0–1000 coordinates without changing evidence", () => {
  const box={x:100,y:200,width:400,height:300,unknown:'synthetic'};
  const before=structuredClone(box);
  assert.deepEqual(bboxGeometry(box,'normalized',640,1280),{x:64,y:256,width:256,height:384});
  assert.deepEqual(bboxGeometry([500,500,100,200],'normalized',640,1280),{x:64,y:256,width:256,height:384});
  assert.deepEqual(box,before);
  assert.deepEqual(bboxGeometry([100,200,500,500],'pixels',640,1280),{x:100,y:200,width:400,height:300});
  assert.equal(bboxGeometry(box,'unknown',640,1280),null);
});

test("invalid, empty and out-of-range boxes never become guessed rectangles", () => {
  for(const box of [[0,0,1001,500],[0,0,0,50],[0,0,Infinity,20],['1',2,3,4],{x:1,y:1,width:-1,height:2},{x:0,y:0,width:100,height:NaN}]) {
    assert.equal(bboxGeometry(box,'normalized',640,1280),null);
  }
});

test("batch proposals preserve order, raw unknowns and non-spatial actions", () => {
  const step={value:{tool_call:{name:'mobile_use',arguments:{action:'batch_actions',batch_actions:[
    {action:'click',coordinate:[500,1000]},
    {action:'type',text:'tap(1,2); "synthetic"\nline',coordinate:[1,2]},
    {action:'system_button',button:'enter'},
    'legacy code is not executable',
    {name:'unknown_tool',arguments:{action:'click',coordinate:[5,6]}},
  ]}}}};
  const before=JSON.stringify(step);
  const projected=projectStep(step);
  assert.deepEqual(projected.actions.map(action=>action.kind),['click','type','system_button','unknown_action','unknown_action']);
  assert.deepEqual(projected.actions.map(action=>action.sequence),[1,2,3,4,5]);
  assert.equal(projected.actions[3].args.raw,'legacy code is not executable');
  assert.match(projected.actions[0].source,/arguments.batch_actions\[0\]/);
  assert.equal(actionMarkers(projected.actions,'normalized',640,1280).length,1);
  assert.equal(JSON.stringify(step),before);
});

test("bare legacy structured batches share projection without evaluating legacy code", () => {
  const actions=projectStep({value:{code:'tap(1,2)',tool_call:{action:'batch_actions',batch_actions:[
    {action:'drag',coordinate:[100,200],coordinate2:[500,600]},
    {name:'mobile_use',arguments:JSON.stringify({action:'click',coordinate:[500,500]})},
  ]}}}).actions;
  assert.equal(actions.length,2);
  assert.deepEqual(actionMarkers(actions,'normalized',1000,1000).map(marker=>marker.geometry),[
    {kind:'motion',points:[100,200,500,600]}, {kind:'point',points:[500,500]},
  ]);
});

test("duplicate markers combine sequence badges without losing distinct motion endpoints", () => {
  const actions=projectStep({value:{tool_call:{action:'batch_actions',batch_actions:[
    {action:'click',coordinate:[500,500]},{action:'click',coordinate:[500,500]},
    {action:'drag',start_coordinate:[500,500],end_coordinate:[600,600]},
    {action:'drag',start_coordinate:[500,500],end_coordinate:[700,700]},
  ]}}}).actions;
  const markers=actionMarkers(actions,'normalized',1000,1000);
  assert.equal(markers.length,3);
  assert.deepEqual(markers[0].sequences,[1,2]);
  assert.equal(markers.filter(marker=>marker.geometry.kind==='motion').length,2);
  assert.deepEqual(actionMarkers(actions,'unknown',1000,1000),[]);
});

test("several batches retain a single unambiguous proposal order", () => {
  const actions=projectStep({value:{tool_call:[
    {name:'mobile_use',arguments:{action:'batch_actions',batch_actions:[{action:'click',coordinate:[1,2]}]}},
    {name:'mobile_use',arguments:{action:'batch_actions',batch_actions:[{action:'wait'},{action:'click',coordinate:[3,4]}]}},
  ]}}).actions;
  assert.deepEqual(actions.map(action=>action.sequence),[1,2,3]);
  assert.match(actions[2].source,/\[1\].arguments.batch_actions\[1\]/);
});
