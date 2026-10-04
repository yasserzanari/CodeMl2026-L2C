"""Regression: entering the progress route must start automatic updates."""
from pathlib import Path
import shutil
import subprocess
import pytest


def test_progress_route_loads_document_metadata_and_schedules_poll():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js unavailable')
    source = (Path(__file__).parents[1]/'l2c_app/static/app.js').read_text('utf-8')
    route = source[source.index('async function route()'):source.index('function schedulePoll()')]
    script = """
const assert=require('node:assert/strict');
const state={}; let rendered,scheduled=0;
const job={id:'job',project_id:'EspCa3B'};
const project={id:'EspCa3B',documents:[{id:'pdf',name:'Plan.pdf'}]};
async function loadOverview(){}
function activeJob(){return job}
function routeParts(){return {page:'progress'}}
async function api(path){assert.equal(path,'/projects/EspCa3B');return project}
function renderProgress(value){rendered=value}
function schedulePoll(){scheduled++}
""" + route + """
route().then(()=>{
 assert.equal(rendered,job);
 assert.equal(state.progressProject,project);
 assert.equal(scheduled,1);
}).catch(error=>{console.error(error);process.exitCode=1});
"""
    subprocess.run([node,'-e',script],check=True,capture_output=True,text=True)


def test_review_filter_uses_server_review_state_parameter():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js unavailable')
    source = (Path(__file__).parents[1]/'l2c_app/static/app.js').read_text('utf-8')
    start = source.index('function makeParams()')
    end = source.index('function resultTabs(', start)
    script = """
const assert=require('node:assert/strict');
const state={filter:{q:'',status:'',family:'',sheet:'',review:'manquant_dans_atelier',offset:0}};
""" + source[start:end] + """
const params=makeParams();
assert.equal(params.get('review_state'),'manquant_dans_atelier');
assert.equal(params.get('review'),null);
"""
    subprocess.run([node,'-e',script],check=True,capture_output=True,text=True)
