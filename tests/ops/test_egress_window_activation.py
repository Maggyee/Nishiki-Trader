"""Atomic blackout preparation and real isolated nft transaction."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "infra/egress-guard"


def load(name):
    path = ROOT / (name + ".py")
    spec = importlib.util.spec_from_file_location(name + "_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_only_fixed_blackout_elements_enter_transaction():
    activation = load("gateway_window_activation")
    calls = []

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, b"", b"")

    activation._write_blackout(5000, runner=runner)
    args, kwargs = calls[0]
    assert args == ["/usr/sbin/nft", "-f", "-"]
    assert kwargs["input"] == (
        b"add element inet trader_joint_window_v1 blackout { ipv4 timeout 5000ms, ipv6 timeout 5000ms }\n"
        b"add element netdev trader_joint_window_v1 blackout { 0x0800 timeout 5000ms, 0x86dd timeout 5000ms }\n"
    )
    assert b"permits" not in kwargs["input"]
    with pytest.raises(ValueError, match="joint_activation_fixed_duration_required"):
        activation._write_blackout(
            "5000ms }\nflush set inet trader_joint_window_v1 permits", runner=runner
        )
    assert len(calls) == 1


@pytest.mark.parametrize("duration", [True, 0, 999, 3_725_001])
def test_invalid_duration_refuses_before_precheck(duration):
    activation = load("gateway_window_activation")

    class Unused:
        snapshotter = None
        seq = 1
        failed = closed = False

    scope = Unused()
    with pytest.raises(ValueError, match="joint_activation_root_fresh_scope_and_duration_required"):
        activation.activate(None, scope, duration_ms=duration)
    assert scope.failed


def test_real_isolated_nft_blackout_transaction_and_uncertain_preparation():
    child = r"""
import importlib.util,json,subprocess,sys,tempfile
from pathlib import Path
base=Path(sys.argv[1])
def load(name):
 spec=importlib.util.spec_from_file_location(name,base/(name+'.py'))
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
kernel=load('gateway_window_kernel')
witness=load('gateway_window_witness')
activation=load('gateway_window_activation')
name=kernel.TABLE
rules=f'''table inet {name} {{
 set blackout {{ type nf_proto; flags timeout; }}
 set permits {{ type ipv4_addr; flags timeout; }}
 chain output {{ type filter hook output priority -310; policy accept; oifname "lo" accept; meta nfproto @blackout counter drop; }}
 chain forward {{ type filter hook forward priority -310; policy accept; meta nfproto @blackout counter drop; }}
}}
table netdev {name} {{
 set blackout {{ type ether_type; flags timeout; }}
 set permits {{ type ipv4_addr; flags timeout; }}
 chain egress {{ type filter hook egress device "lo" priority 0; policy accept; ether type @blackout counter drop; }}
}}'''
created=subprocess.run(['/usr/sbin/nft','-f','-'],input=rules.encode(),capture_output=True)
if created.returncode: raise RuntimeError(created.stderr.decode())
pins={family:kernel.digest(kernel._static(kernel.read_table(family)['nftables'])) for family in kernel.KINDS}
class Held:
 def __init__(self): self.closed=False
 def inspect_inactive(self):
  for family in kernel.KINDS:
   kernel.inspect_table(kernel.read_table(family),family,expected_static_sha256=pins[family],wan_interface='lo',chain_text=kernel.read_netdev_chain() if family=='netdev' else None,expect_inactive=True)
  return {'schema_version':'portfolio.root_selected_joint_window_inactive.v1','status':'selected_empty_blackout_and_permits_unqualified','selection_sha256':'a'*64,'static_rules_sha256':pins,'network_admitted':False}
 def observe(self):
  return {'schema_version':'portfolio.root_selected_joint_window_snapshot.v1','status':'root_selected_kernel_snapshot_unqualified','selection_sha256':'a'*64,'kernel_snapshot':kernel.observe(expected_static_sha256=pins,wan_interface='lo'),'activation_history_verified':False,'source_authenticated':False,'complete_caller_coverage_verified':False,'network_admitted':False}
 def close(self): self.closed=True
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp)
 failed=Held(); first=witness.WindowWitness(root,failed)
 def reject(*args,**kwargs): return subprocess.CompletedProcess(args,1,b'',b'fixture failure')
 try: activation.activate(failed,first,duration_ms=5000,runner=reject)
 except ValueError as exc: assert 'joint_activation_kernel_transaction_failed' in str(exc)
 else: raise RuntimeError('failed transaction accepted')
 pending=witness.replay(first.expected,expected_sha256=witness.digest(first.expected))
 assert first.failed and failed.closed and pending['activation_prepared'] and pending['observations']==0
 assert not kernel.read_table('inet')['nftables'][2]['set'].get('elem')
 first.close()
 second=Held(); scope=root/'second';scope.mkdir(mode=0o700)
 journal=witness.WindowWitness(scope,second)
 report=activation.activate(second,journal,duration_ms=5000)
 archived=witness.replay(journal.expected,expected_sha256=witness.digest(journal.expected))
 assert archived['activation_prepared'] and archived['observations']==1
 assert report['network_admitted'] is False and report['activation_history_verified'] is False
 for family in kernel.KINDS:
  sets=[row['set'] for row in kernel.read_table(family)['nftables'] if 'set' in row]
  assert not next(item for item in sets if item['name']=='permits').get('elem')
 try: activation.activate(second,journal,duration_ms=5000)
 except ValueError: pass
 else: raise RuntimeError('second activation accepted')
 journal.close()
 print(json.dumps({'status':report['status'],'prepared':pending['activation_prepared'],'observations':archived['observations'],'network_admitted':report['network_admitted']}))
"""
    result = subprocess.run(
        ["/usr/bin/unshare", "-Urn", sys.executable, "-I", "-c", child, str(ROOT)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    report = json.loads(result.stdout)
    assert report == {
        "status": "local_blackout_transaction_observed_unqualified",
        "prepared": True,
        "observations": 1,
        "network_admitted": False,
    }
