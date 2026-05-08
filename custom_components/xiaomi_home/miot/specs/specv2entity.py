# -*- coding: utf-8 -*-
"""
Conversion rules of MIoT-Spec-V2 instance to Home Assistant entity.
"""
from types import MappingProxyType

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor import SensorStateClass
from homeassistant.components.event import EventDeviceClass
from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from homeassistant.const import (CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
                                 EntityCategory, LIGHT_LUX, UnitOfEnergy,
                                 UnitOfPower, UnitOfElectricCurrent,
                                 UnitOfElectricPotential, UnitOfTemperature,
                                 UnitOfPressure, PERCENTAGE)

# 優化：定義共用的不可變權限常數，減少記憶體重複配置
_R = frozenset({'read'})
_W = frozenset({'write'})
_RW = frozenset({'read', 'write'})

# pylint: disable=pointless-string-statement
"""SPEC_DEVICE_TRANS_MAP
{
    '<device instance name>':{
        'required':{
            '<service instance name>':{
                'required':{
                    'properties': {
                        '<property instance name>': frozenset<property access: str>
                    },
                    'events': frozenset<event instance name: str>,
                    'actions': frozenset<action instance name: str>
                },
                'optional':{
                    'properties': frozenset<property instance name: str>,
                    'events': frozenset<event instance name: str>,
                    'actions': frozenset<action instance name: str>
                }
            }
        },
        'optional':{
            '<service instance name>':{
                'required':{
                    'properties': {
                        '<property instance name>': frozenset<property access: str>
                    },
                    'events': frozenset<event instance name: str>,
                    'actions': frozenset<action instance name: str>
                },
                'optional':{
                    'properties': frozenset<property instance name: str>,
                    'events': frozenset<event instance name: str>,
                    'actions': frozenset<action instance name: str>
                }
            }
        },
        'entity': str
    }
}
"""

# 優化：使用 MappingProxyType 與 frozenset 保護常數不被意外竄改
SPEC_DEVICE_TRANS_MAP = MappingProxyType({
    'humidifier': {
        'required': {
            'humidifier': {
                'required': {
                    'properties': {
                        'on': _RW
                    }
                },
                'optional': {
                    'properties': frozenset({'mode', 'target-humidity'})
                }
            }
        },
        'optional': {
            'environment': {
                'required': {
                    'properties': {
                        'relative-humidity': _R
                    }
                }
            }
        },
        'entity': 'humidifier'
    },
    'dehumidifier': {
        'required': {
            'dehumidifier': {
                'required': {
                    'properties': {
                        'on': _RW
                    }
                },
                'optional': {
                    'properties': frozenset({'mode', 'target-humidity'})
                }
            }
        },
        'optional': {
            'environment': {
                'required': {
                    'properties': {
                        'relative-humidity': _R
                    }
                }
            }
        },
        'entity': 'dehumidifier'
    },
    'vacuum': {
        'required': {
            'vacuum': {
                'required': {
                    'actions': frozenset({'start-sweep', 'stop-sweeping'}),
                },
                'optional': {
                    'properties': frozenset({'status', 'fan-level'}),
                    'actions': frozenset({
                        'pause-sweeping', 'continue-sweep', 'stop-and-gocharge'
                    })
                }
            }
        },
        'optional': {
            'identify': {
                'required': {
                    'actions': frozenset({'identify'})
                }
            },
            'battery': {
                'required': {
                    'actions': frozenset({'start-charge'})
                }
            }
        },
        'entity': 'vacuum'
    },
    'air-conditioner': {
        'required': {
            'air-conditioner': {
                'required': {
                    'properties': {
                        'on': _RW,
                        'mode': _RW,
                        'target-temperature': _RW
                    }
                },
                'optional': {
                    'properties': frozenset({'target-humidity'})
                }
            }
        },
        'optional': {
            'fan-control': {
                'required': {},
                'optional': {
                    'properties': frozenset({
                        'on', 'fan-level', 'horizontal-swing', 'vertical-swing'
                    })
                }
            },
            'environment': {
                'required': {},
                'optional': {
                    'properties': frozenset({'temperature', 'relative-humidity'})
                }
            },
            'air-condition-outlet-matching': {
                'required': {},
                'optional': {
                    'properties': frozenset({'ac-state'})
                }
            }
        },
        'entity': 'air-conditioner'
    },
    'air-condition-outlet': 'air-conditioner',
    'thermostat': {
        'required': {
            'thermostat': {
                'required': {
                    'properties': {
                        'on': _RW
                    }
                },
                'optional': {
                    'properties': frozenset({
                        'target-temperature', 'mode', 'fan-level', 'temperature'
                    })
                }
            }
        },
        'optional': {
            'environment': {
                'required': {},
                'optional': {
                    'properties': frozenset({'temperature', 'relative-humidity'})
                }
            }
        },
        'entity': 'thermostat'
    },
    'heater': {
        'required': {
            'heater': {
                'required': {
                    'properties': {
                        'on': _RW
                    }
                },
                'optional': {
                    'properties': frozenset({'target-temperature', 'heat-level'})
                }
            }
        },
        'optional': {
            'environment': {
                'required': {},
                'optional': {
                    'properties': frozenset({'temperature', 'relative-humidity'})
                }
            }
        },
        'entity': 'heater'
    },
    'bath-heater': {
        'required': {
            'ptc-bath-heater': {
                'required': {
                    'properties': {
                        'mode': _RW
                    }
                },
                'optional': {
                    'properties': frozenset({'target-temperature', 'temperature'})
                }
            }
        },
        'optional': {
            'fan-control': {
                'required': {},
                'optional': {
                    'properties': frozenset({
                        'on', 'fan-level', 'horizontal-swing', 'vertical-swing'
                    })
                }
            },
            'environment': {
                'required': {},
                'optional': {
                    'properties': frozenset({'temperature'})
                }
            }
        },
        'entity': 'bath-heater',
    },
    'electric-blanket': {
        'required': {
            'electric-blanket': {
                'required': {
                    'properties': {
                        'on': _RW,
                        'target-temperature': _RW
                    }
                },
                'optional': {
                    'properties': frozenset({'mode', 'temperature'})
                }
            }
        },
        'optional': {},
        'entity': 'electric-blanket'
    },
    'speaker': {
        'required': {
            'speaker': {
                'required': {
                    'properties': {
                        'volume': _RW
                    }
                },
                'optional': {
                    'properties': frozenset({'mute'})
                }
            },
            'play-control': {
                'required': {
                    'properties': {
                        'playing-state': _R
                    },
                    'actions': frozenset({'play'})
                },
                'optional': {
                    'properties': frozenset({'play-loop-mode'}),
                    'actions': frozenset({'pause', 'stop', 'next', 'previous'})
                }
            }
        },
        'optional': {},
        'entity': 'wifi-speaker'
    },
    'television': {
        'required': {
            'speaker': {
                'required': {
                    'properties': {
                        'volume': _RW
                    }
                },
                'optional': {
                    'properties': frozenset({'mute'})
                }
            },
            'television': {
                'required': {
                    'actions': frozenset({'turn-off'})
                },
                'optional': {
                    'properties': frozenset({'input-control'}),
                    'actions': frozenset({'turn-on'})
                }
            }
        },
        'optional': {
            'play-control': {
                'required': {
                    'properties': {
                        'playing-state': _R
                    }
                },
                'optional': {
                    'properties': frozenset({'play-loop-mode'}),
                    'actions': frozenset({'play', 'pause', 'stop', 'next', 'previous'})
                }
            }
        },
        'entity': 'television'
    },
    'tv-box':{
        'required': {
            'speaker': {
                'required': {
                    'properties': {
                        'volume': _RW
                    }
                },
                'optional': {
                    'properties': frozenset({'mute'})
                }
            },
            'tv-box': {
                'required': {
                    'actions': frozenset({'turn-off'})
                },
                'optional': {
                    'actions': frozenset({'turn-on'})
                }
            }
        },
        'optional': {
            'play-control': {
                'required': {
                    'properties': {
                        'playing-state': _R
                    }
                },
                'optional': {
                    'properties': frozenset({'play-loop-mode'}),
                    'actions': frozenset({'play', 'pause', 'stop', 'next', 'previous'})
                }
            }
        },
        'entity': 'television'
    },
    'watch': {
        'required': {
            'watch': {
                'required': {
                    'properties': {
                        'longitude': _R,
                        'latitude': _R
                    }
                },
                'optional': {
                    'properties': frozenset({'area-id'})
                }
            }
        },
        'optional': {
            'battery': {
                'required': {
                    'properties': {
                        'battery-level': _R
                    }
                }
            }
        },
        'entity': 'device_tracker'
    }
})

"""SPEC_SERVICE_TRANS_MAP
{
    '<service instance name>':{
        'required':{
            'properties': {
                '<property instance name>': frozenset<property access: str>
            },
            'events': frozenset<event instance name: str>,
            'actions': frozenset<action instance name: str>
        },
        'optional':{
            'properties': frozenset<property instance name: str>,
            'events': frozenset<event instance name: str>,
            'actions': frozenset<action instance name: str>
        },
        'entity': str,
        'entity_category'?: str
    }
}
"""
SPEC_SERVICE_TRANS_MAP = MappingProxyType({
    'light': {
        'required': {
            'properties': {
                'on': _RW
            }
        },
        'optional': {
            'properties': frozenset({'mode', 'brightness', 'color', 'color-temperature'})
        },
        'entity': 'light'
    },
    'ambient-light': 'light',
    'night-light': 'light',
    'white-light': 'light',
    'indicator-light': {
        'required': {
            'properties': {
                'on': _RW
            }
        },
        'optional': {
            'properties': frozenset({
                'mode',
                'brightness',
            })
        },
        'entity': 'light',
        'entity_category': EntityCategory.CONFIG
    },
    'fan': {
        'required': {
            'properties': {
                'on': _RW,
                'fan-level': _RW
            }
        },
        'optional': {
            'properties': frozenset({'mode', 'horizontal-swing', 'wind-reverse'})
        },
        'entity': 'fan'
    },
    'fan-control': 'fan',
    'ceiling-fan': 'fan',
    'air-fresh': 'fan',
    'air-purifier': 'fan',
    'water-heater': {
        'required': {
            'properties': {
                'on': _RW
            }
        },
        'optional': {
            'properties': frozenset({'temperature', 'target-temperature', 'mode'})
        },
        'entity': 'water_heater'
    },
    'curtain': {
        'required': {
            'properties': {
                'motor-control': _W
            }
        },
        'optional': {
            'properties': frozenset({'status', 'current-position', 'target-position'})
        },
        'entity': 'cover'
    },
    'window-opener': 'curtain',
    'motor-controller': 'curtain',
    'airer': 'curtain',
    'air-conditioner': {
        'required': {
            'properties': {
                'on': _RW,
                'mode': _RW,
                'target-temperature': _RW
            }
        },
        'optional': {
            'properties': frozenset({'target-humidity'})
        },
        'entity': 'air-conditioner'
    }
})

"""SPEC_PROP_TRANS_MAP
{
    'entities':{
        '<entity name>':{
            'format': frozenset<str>,
            'access': frozenset<str>
        }
    },
    'properties': {
        '<property instance name>':{
            'device_class': str,
            'entity': str,
            'state_class'?: str,
            'unit_of_measurement'?: str
        }
    }
}
"""
SPEC_PROP_TRANS_MAP = MappingProxyType({
    'entities': {
        'sensor': {
            'format': frozenset({'int', 'float'}),
            'access': _R
        },
        'binary_sensor': {
            'format': frozenset({'bool', 'int'}),
            'access': _R
        },
        'switch': {
            'format': frozenset({'bool'}),
            'access': _RW
        }
    },
    'properties': {
        'submersion-state': {
            'device_class': BinarySensorDeviceClass.MOISTURE,
            'entity': 'binary_sensor'
        },
        'contact-state': {
            'device_class': BinarySensorDeviceClass.DOOR,
            'entity': 'binary_sensor'
        },
        'occupancy-status': {
            'device_class': BinarySensorDeviceClass.OCCUPANCY,
            'entity': 'binary_sensor',
        },
        'temperature': {
            'device_class': SensorDeviceClass.TEMPERATURE,
            'entity': 'sensor',
            'state_class': SensorStateClass.MEASUREMENT,
            'unit_of_measurement': UnitOfTemperature.CELSIUS
        },
        'relative-humidity': {
            'device_class': SensorDeviceClass.HUMIDITY,
            'entity': 'sensor',
            'state_class': SensorStateClass.MEASUREMENT,
            'unit_of_measurement': PERCENTAGE
        },
        'air-quality-index': {
            'device_class': SensorDeviceClass.AQI,
            'entity': 'sensor',
            'state_class': SensorStateClass.MEASUREMENT,
        },
        'pm2.5-density': {
            'device_class': SensorDeviceClass.PM25,
            'entity': 'sensor',
            'state_class': SensorStateClass.MEASUREMENT,
            'unit_of_measurement': CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
        },
        'pm10-density': {
            'device_class': SensorDeviceClass.PM10,
            'entity': 'sensor',
            'state_class': SensorStateClass.MEASUREMENT,
            'unit_of_measurement': CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
        },
        'pm1': {
            'device_class': SensorDeviceClass.PM1,
            'entity': 'sensor',
            'state_class': SensorStateClass.MEASUREMENT,
            'unit_of_measurement': CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
        },
        'atmospheric-pressure': {
            'device_class': SensorDeviceClass.ATMOSPHERIC_PRESSURE,
            'entity': 'sensor',
            'state_class': SensorStateClass.MEASUREMENT,
            'unit_of_measurement': UnitOfPressure.PA
        },
        'tvoc-density': {
            'device_class': SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
            'entity': 'sensor',
            'state_class': SensorStateClass.MEASUREMENT
        },
        'voc-density': {
            'device_class': SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS_PARTS,
            'entity': 'sensor',
            'state_class': SensorStateClass.MEASUREMENT
        },
        'battery-level': {
            'device_class': SensorDeviceClass.BATTERY,
            'entity': 'sensor',
            'state_class': SensorStateClass.MEASUREMENT,
            'unit_of_measurement': PERCENTAGE
        },
        'voltage': {
            'device_class': SensorDeviceClass.VOLTAGE,
            'entity': 'sensor',
            'state_class': SensorStateClass.MEASUREMENT,
            'unit_of_measurement': UnitOfElectricPotential.VOLT
        },
        'electric-current': {
            'device_class': SensorDeviceClass.CURRENT,
            'entity': 'sensor',
            'state_class': SensorStateClass.MEASUREMENT,
            'unit_of_measurement': UnitOfElectricCurrent.AMPERE
        },
        'illumination': {
            'device_class': SensorDeviceClass.ILLUMINANCE,
            'entity': 'sensor',
            'state_class': SensorStateClass.MEASUREMENT,
            'unit_of_measurement': LIGHT_LUX
        },
        'no-one-determine-time': {
            'device_class': SensorDeviceClass.DURATION,
            'entity': 'sensor'
        },
        'has-someone-duration': 'no-one-determine-time',
        'no-one-duration': 'no-one-determine-time',
        'electric-power': {
            'device_class': SensorDeviceClass.POWER,
            'entity': 'sensor',
            'state_class': SensorStateClass.MEASUREMENT,
            'unit_of_measurement': UnitOfPower.WATT
        },
        'surge-power': {
            'device_class': SensorDeviceClass.POWER,
            'entity': 'sensor',
            'state_class': SensorStateClass.MEASUREMENT,
            'unit_of_measurement': UnitOfPower.WATT
        },
        'power-consumption': {
            'device_class': SensorDeviceClass.ENERGY,
            'entity': 'sensor',
            'state_class': SensorStateClass.TOTAL_INCREASING,
            'unit_of_measurement': UnitOfEnergy.KILO_WATT_HOUR
        },
        'power': {
            'device_class': SensorDeviceClass.POWER,
            'entity': 'sensor',
            'state_class': SensorStateClass.MEASUREMENT,
            'unit_of_measurement': UnitOfPower.WATT
        }
    }
})

"""SPEC_EVENT_TRANS_MAP
{
    '<event instance name>': str
}
"""
SPEC_EVENT_TRANS_MAP = MappingProxyType({
    'click': EventDeviceClass.BUTTON,
    'double-click': EventDeviceClass.BUTTON,
    'long-press': EventDeviceClass.BUTTON,
    'motion-detected': EventDeviceClass.MOTION,
    'no-motion': EventDeviceClass.MOTION,
    'doorbell-ring': EventDeviceClass.DOORBELL
})

SPEC_ACTION_TRANS_MAP = MappingProxyType({})
