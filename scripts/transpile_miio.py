import sys
import os
import json
from copy import deepcopy
import pprint

# Define the absolute path to the hass-xiaomi-miot core models
HASS_XIAOMI_MIOT_DIR = os.environ.get("HASS_XIAOMI_MIOT_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "../../hass-xiaomi-miot-master")))
sys.path.append(os.path.join(HASS_XIAOMI_MIOT_DIR, "custom_components/xiaomi_miot/core"))

try:
    from miio2miot_specs import MIIO_TO_MIOT_SPECS
except Exception as e:
    print(f"Error importing MIIO_TO_MIOT_SPECS. Ensure {HASS_XIAOMI_MIOT_DIR} exists.")
    sys.exit(1)

# --- 1. Define the 19 Hyper-Focused Whitelist Models ---
WHITELIST = []
for model in MIIO_TO_MIOT_SPECS.keys():
    if (model.startswith('yeelink.light.lamp') or 
        model.startswith('yeelink.light.bslamp') or 
        model.startswith('zhimi.fan.') or 
        model.startswith('dmaker.fan.')):
        WHITELIST.append(model)

# --- 2. Resolve `extend_model` Flattening ---
def resolve_model(model_name, spec_dict):
    spec = spec_dict.get(model_name)
    if not spec:
        return {}
    if isinstance(spec, str):
        return resolve_model(spec, spec_dict)
    
    resolved = deepcopy(spec)
    if 'extend_model' in resolved:
        parent_model = resolved['extend_model']
        parent_spec = resolve_model(parent_model, spec_dict)
        
        # Merge parent into child (child overrides parent)
        merged = deepcopy(parent_spec)
        if 'miio_specs' in resolved:
            if 'miio_specs' not in merged:
                merged['miio_specs'] = {}
            # Update miio_specs recursively
            for k, v in resolved['miio_specs'].items():
                if v and isinstance(v, dict) and k in merged['miio_specs'] and isinstance(merged['miio_specs'][k], dict):
                    merged['miio_specs'][k].update(v)
                else:
                    merged['miio_specs'][k] = v
                    
        # Merge other top level keys
        for k, v in resolved.items():
            if k not in ['miio_specs', 'extend_model']:
                merged[k] = v
                
        # Remove extend_model as it is now flattened
        if 'extend_model' in merged:
            del merged['extend_model']
        return merged
        
    return resolved

flattened_specs = {}
for model in WHITELIST:
    flattened_specs[model] = resolve_model(model, MIIO_TO_MIOT_SPECS)

# --- 3. Static Jinja to Python Lambda Mapping ---
JINJA_TO_PYTHON = {
    '{{ ["on" if value else "off","smooth",500] }}': 'lambda value, props, max_val: ["on" if value else "off", "smooth", 500]',
    '{{ [value|int] }}': 'lambda value, props, max_val: [int(value)]',
    '{{ ["auto_delay_off",props.bright|default(100)|int,value] }}': 'lambda value, props, max_val: ["auto_delay_off", int(props.get("bright", 100)), value]',
    '{{ value|int(0) > 0 }}': 'lambda value, props, max_val: int(value or 0) > 0',
    '{% set nlv = props.natural_level|default(0)|int(0) %}{{ {"method": "set_natural_level" if nlv else "set_speed_level","params": [value|int(0)],} }}': 'lambda value, props, max_val: {"method": "set_natural_level" if int(props.get("natural_level", 0)) else "set_speed_level", "params": [int(value or 0)]}',
    '{% set nlb = props.nl_br|default(0)|int(0) %}{{ nlb if nlb else value }}': 'lambda value, props, max_val: int(props.get("nl_br", 0)) if int(props.get("nl_br", 0)) else value',
    '{% set lvl = props.natural_level|default(value,true)|int(0) %}{{ lvl if max == 100 else 1 if lvl <= 25 else 2 if lvl <= 50 else 3 if lvl <= 75 else 4 }}': 'lambda value, props, max_val: (int(props.get("natural_level", value) or 0) if max_val == 100 else (1 if int(props.get("natural_level", value) or 0) <= 25 else (2 if int(props.get("natural_level", value) or 0) <= 50 else (3 if int(props.get("natural_level", value) or 0) <= 75 else 4))))',
    '{{ 1 if value|int(0) > 0 else 2 }}': 'lambda value, props, max_val: 1 if int(value or 0) > 0 else 2',
    '{{ 2 if value == "complete" else 1 }}': 'lambda value, props, max_val: 2 if value == "complete" else 1',
    '{% set nlv = props.natural_level|default(0)|int(0) %}{{ {"method": "set_natural_level" if nlv else "set_speed_level","params": [value|int(0) * (1 if max == 100 else 25)],} }}': 'lambda value, props, max_val: {"method": "set_natural_level" if int(props.get("natural_level", 0)) else "set_speed_level", "params": [int(value or 0) * (1 if max_val == 100 else 25)]}',
    '{{ 1 if value|int(0) > 0 else 0 }}': 'lambda value, props, max_val: 1 if int(value or 0) > 0 else 0',
    '{{ [value,"smooth",500] }}': 'lambda value, props, max_val: [value, "smooth", 500]',
    '{{ [value|int(0) * 25] }}': 'lambda value, props, max_val: [int(value or 0) * 25]',
    '{{ (value/25)|round }}': 'lambda value, props, max_val: round(value/25)',
    '{{ [(value*25)|round] }}': 'lambda value, props, max_val: [round(value*25)]',
    '{{ [1 if value else 0] }}': 'lambda value, props, max_val: [1 if value else 0]',
    '{{ props.natural_level|default(value,true)|int(0) }}': 'lambda value, props, max_val: int(props.get("natural_level", value) or 0)',
    '{{ ["nightlight","on" if value == 2 else "off"] }}': 'lambda value, props, max_val: ["nightlight", "on" if value == 2 else "off"]',
    '{{ 2 if value|int else 1 }}': 'lambda value, props, max_val: 2 if int(value) else 1'
}

# --- 4. Format into Python Source Code ---
output_lines = [
    '# This file is auto-generated by scripts/transpile_miio.py',
    '# Do not edit manually. Edit the build script instead.',
    '',
    'MIIO_SPECS = {'
]

for model in sorted(flattened_specs.keys()):
    spec = flattened_specs[model]
    output_lines.append(f'    "{model}": {{')
    
    if 'chunk_properties' in spec:
        output_lines.append(f'        "chunk_properties": {spec["chunk_properties"]},')
        
    if 'miio_commands' in spec:
        # Keep miio_commands as is but use valid python types
        output_lines.append(f'        "miio_commands": {repr(spec["miio_commands"])},')
        
    if 'miio_specs' in spec:
        output_lines.append(f'        "miio_specs": {{')
        for prop_id, prop_cfg in spec['miio_specs'].items():
            # If the prop is null, it means it's explicitly deleted by a child
            if not prop_cfg or prop_cfg.get('prop') is None:
                continue
                
            output_lines.append(f'            "{prop_id}": {{')
            for k, v in prop_cfg.items():
                if k in ['template', 'set_template']:
                    if v in JINJA_TO_PYTHON:
                        output_lines.append(f'                "{k}": {JINJA_TO_PYTHON[v]},')
                    else:
                        print(f"WARNING: Unknown Jinja template '{v}' in {model}.{prop_id}")
                else:
                    if isinstance(v, str):
                        output_lines.append(f'                "{k}": "{v}",')
                    elif isinstance(v, dict):
                        output_lines.append(f'                "{k}": {repr(v)},')
                    elif isinstance(v, bool):
                        output_lines.append(f'                "{k}": {v},')
                    elif v is None:
                        output_lines.append(f'                "{k}": None,')
                    else:
                        output_lines.append(f'                "{k}": {v},')
            output_lines.append(f'            }},')
        output_lines.append(f'        }}')
        
    output_lines.append(f'    }},')

output_lines.append('}')
output_lines.append('')

output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "custom_components/xiaomi_home/miot/miio_specs.py")
os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, "w") as f:
    f.write("\n".join(output_lines))

print(f"Successfully transpiled {len(flattened_specs)} models to {output_path}")
