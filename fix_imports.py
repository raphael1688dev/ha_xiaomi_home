import glob

for file in glob.glob('custom_components/xiaomi_home/config_flow/*.py'):
    with open(file, 'r') as f:
        content = f.read()
    content = content.replace('from .miot', 'from ..miot')
    with open(file, 'w') as f:
        f.write(content)
