import re

def add_exception_logging(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Replace _LOGGER.error(..., err) with _LOGGER.exception(...) when inside except block
    # A simple regex to find `except Exception as err:` followed by a `_LOGGER.error` line
    
    # We will just change `_LOGGER.error` to `_LOGGER.exception` in except Exception as err: blocks
    # Actually, if we just do a string replacement of `_LOGGER.error(` to `_LOGGER.exception(` if it has `err)` 
    # it might be too broad. Let's just do it manually for a few files since it's just 6 places in lan and a few in cloud.
    
    # Let's replace: _LOGGER.error('some text %s', err) with _LOGGER.exception('some text %s', err)
    
    def repl(m):
        return m.group(0).replace('_LOGGER.error', '_LOGGER.exception')
        
    content = re.sub(r'except Exception as err:\n\s+_LOGGER\.error\([^)]+err\)', repl, content)
    
    with open(filepath, 'w') as f:
        f.write(content)

add_exception_logging('custom_components/xiaomi_home/miot/miot_lan.py')
add_exception_logging('custom_components/xiaomi_home/miot/miot_cloud.py')
