Pluguin de Qgis para realizar la importación de los datos de la hoja de cáculo adjunta a la solicitud de inscripción en el registro de itinierarios deportivos y catalogo de instalaciones recreattivas del a Generalitat Valenciana.
Puede usuarse tanto por los técnicos para la evaluación del itinerario como por los solicitantes para comprovar gráficamente la localización de los datos.

1. Isntalación.</br>
   El pluguin de momento no esta en el repositorio oficial de QGIS se puede descargar en formato ZIP e instalarlo.
   https://docs.qgis.org/3.40/es/docs/user_manual/plugins/plugins.html
2. Ejecución.</br>
Antes de ejecutar el pluguint tienes que tener cargdos en Qgis el track del itinerario y la hoja de cálculo (formato XLS o ODS), ambos los puedes cargar arrastrando y soltando sobre qgis.
Para ejecutar el pluguin tan solo tienes que selecciarlo desde el menu Complementos>Itinerarios>Tramos sobre track (25830), o bien con el icono 
<img src="https://github.com/pauarago/itinerarios_deportivos_gva/blob/main/icons/sendas.svg" alt="Alt Text" style="width:2%; height:auto;">, se abrira la ventana siguiente;

<img width="902" height="409" alt="image" src="https://github.com/user-attachments/assets/bbe68527-320b-4def-b6d5-25fb3bc4a0a8" />
Nota: por defecto, el sistema utilizado para importar los puntos es el EPSG:25830 (UTM ETRS89 HUSO 30), se puede seleccionar un sistema de coordenadas distinto.</br>
4. Resultado. </br>
Como resultado obtines las siguetes capas:
tramos_itinerario_25830 (capa con los tramos descritos en la hoja de cálculo)
tramos_itinerario_25830_ubicaciones_pts (puntos de las ubicaciones descritas en la hoja de cálculo)
tramos_itinerario_25830_aux (opcional, representa las líneas de intersección de los puntos de la hoja de cálculo "evaluacion_itinerario" con el track)
tramos_itinerario_25830_aux_pts (opcional puntos descritos en las coordenadas de la pestaña de la hoja de cáclulo de "evaluacion_itinerario")
El sistema de coordenadas de las capas de salida es EPSG:25830 (UTM ETRS89 HUSO 30)</br>
</br> 

El incono utilizado en la barra de herramientas se puede descargar aquí, https://www.reshot.com/free-svg-icons/item/road-tracking-QCT3SNWK45/
