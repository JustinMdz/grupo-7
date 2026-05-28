# Trabajo en Clase: Plataforma de Chat Móvil
**Universidad Nacional, Sede Regional Brunca**  
**Curso:** EIF211 – Programación de plataformas móviles  
**Profesor:** Daniel Granados Murillo  


##  Descripción del Proyecto
Este repositorio contiene la base del backend para nuestra aplicación de chat. El objetivo de este trabajo en clase es colaborar de manera distribuida entre todos los grupos del curso para convertir este prototipo en un backend robusto, seguro y con funcionalidades avanzadas de mensajería móvil.



##  Asignación de Tareas por Grupo

###  Grupo 1 – Gestión de Repositorio y Code Review
Este grupo se encargará de la infraestructura del código, la integración de las contribuciones y el control de calidad del proyecto.
* **Tareas principales:**
  - Crear un fork o nuevo repositorio a partir del backend base.
  - Publicarlo y dar acceso a todos los compañeros del curso.
  - Definir la estrategia de ramas (*Branching Strategy*).
  - Revisar, validar y ejecutar los *Merge Requests* / *Pull Requests* de los Grupos 2 al 7.
  - Asegurar la correcta unión del código sin conflictos.

###  Grupo 2 – Persistencia de Datos (SQLite / Firebase)
Responsables del almacenamiento persistente de los mensajes en el servidor.
* **Tareas principales:**
  - Configurar e integrar una base de datos (SQLite en servidor o Firebase) exclusiva para esta función.
  - Diseñar el modelo/tabla de datos para los mensajes (remitente, contenido, fecha, etc.).
  - Crear los endpoints/servicios para guardar y recuperar el historial de chats.

###  Grupo 3 – Seguridad y Autenticación (JWT)
Encargados de restringir el acceso al backend para garantizar la privacidad de los usuarios.
* **Tareas principales:**
  - Investigar e implementar seguridad mediante JSON Web Tokens (JWT) u otro mecanismo similar.
  - Desarrollar endpoints para registro e inicio de sesión (*Login*).
  - Crear middlewares para proteger las rutas del API del chat.

###  Grupo 4 – Encriptación de Mensajes
Este equipo asegurará la confidencialidad de las conversaciones transmitidas.
* **Tareas principales:**
  - Investigar e implementar algoritmos de cifrado simétrico o asimétrico.
  - Desarrollar la lógica para encriptar los mensajes antes de ser enviados/almacenados.
  - Implementar la desencriptación solo cuando el destinatario legítimo acceda al mensaje.

###  Grupo 5 – Gestión Multimedia (Cloudinary)
Extenderán las capacidades del chat permitiendo compartir archivos de forma eficiente.
* **Tareas principales:**
  - Integrar el servicio de Cloudinary en el backend para almacenamiento de archivos.
  - Crear endpoints para la subida de imágenes y archivos multimedia desde la app móvil.
  - Retornar y mapear las URLs correspondientes en la estructura del mensaje para su descarga/acceso por el receptor.

###  Grupo 6 – Mensajes Temporales y Permisos
Añadirán características avanzadas de privacidad sobre el ciclo de vida de los mensajes.
* **Tareas principales:**
  - Gestionar permisos avanzados sobre la visualización de los mensajes.
  - Implementar la funcionalidad de **Mensajes Temporales** (mensajes que se auto-destruyen tras un tiempo determinado).
  - Programar la lógica del backend para ocultar o eliminar el contenido expirado.

###  Grupo 7 – Estado en Tiempo Real y Moderación
Enriquecerán el feedback de la interfaz y añadirán una capa de control de contenido.
* **Tareas principales:**
  - Implementar el estado de los mensajes (sección de vistos / doble check).
  - Añadir el indicador interactivo en tiempo real de *"El usuario está escribiendo..."*.
  - Investigar y desarrollar un algoritmo/librería para identificar y censurar palabras inadecuadas u ofensivas antes de distribuir el mensaje.


##  Flujo de Trabajo y Entregas (Para los Grupos 2 al 7)

Para garantizar el orden del proyecto, todos los grupos deben seguir este flujo de trabajo:

Hacer un fork de este repo, y cuando ya tienen todo listo hacen pull request a este.
4. Al finalizar, abrir un **Pull Request / Merge Request** hacia la rama principal.
5. Notificar al **Grupo 1** para la revisión de código y la aprobación final del *merge*.
