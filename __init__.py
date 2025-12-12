
# -*- coding: utf-8 -*-
def classFactory(iface):
    from .tramos_itinerario import TramosItinerarioPlugin
    return TramosItinerarioPlugin(iface)
