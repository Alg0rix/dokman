

# Dokman

Dokman es una herramienta CLI de Python para la gestión centralizada de implementaciones de Docker Compose. Proporciona una interfaz unificada para administrar implementaciones de Docker Compose desde cualquier directorio sin necesidad de navegar a las ubicaciones individuales de los archivos compose.

## Características

- Listar y monitorear todas las implementaciones de Docker Compose desde una única ubicación
- Iniciar, detener, reiniciar y volver a implementar servicios sin cambiar de directorio
- Ver registros, ejecutar comandos e inspeccionar el estado de salud de los contenedores
- Administrar imágenes, volúmenes y redes entre proyectos
- Rastrear proyectos con un registro local para una gestión persistente
- Salida terminal enriquecida con opciones de formato en tabla y JSON

## Requisitos

- Python 3.13 o superior
- Motor de Docker con Docker Compose v2
- uv (recomendado para la instalación) o pip

## Instalación

### Instalación rápida (Recomendada)

La forma más fácil de instalar dokman es utilizando el script de instalación:

```bash
curl -fsSL https://raw.githubusercontent.com/Alg0rix/dokman/main/install.sh | bash
```

Esto instalará automáticamente [uv](https://docs.astral.sh/uv/) si es necesario y configurará dokman.

### Actualización

Para actualizar a la última versión, ejecute el script de instalación nuevamente o utilice:

```bash
uv tool upgrade dokman
```

### Usando uv

Si ya tiene uv instalado:

```bash
uv tool install --python 3.13 dokman

# Verify installation
dokman --help
```

### Usando pip

```bash
pip install dokman
```

### Desde el código fuente

```bash
# Clone the repository
git clone https://github.com/Alg0rix/dokman.git
cd dokman

# Install dependencies
uv sync

# Run dokman
uv run dokman --help
```

## Inicio rápido

### Registrar un proyecto

Registre un proyecto existente de Docker Compose para su seguimiento:

```bash
# Register from compose file path
dokman register /path/to/docker-compose.yml

# Register with custom name
dokman register /path/to/project --name myapp
```

### Iniciar un proyecto

Inicie un proyecto directamente (se registra automáticamente si es necesario):

```bash
# Start from current directory
dokman up

# Start from specific path
dokman up -f /path/to/project

# Start with custom name
dokman up -f ./myproject -n myapp
```

### Listar proyectos

```bash
# List registered projects
dokman list

# Include unregistered running projects
dokman list --all

# Output as JSON
dokman list --format json
```

### Administrar servicios

```bash
# View project details
dokman info myproject

# Start/stop/restart services
dokman start myproject
dokman stop myproject
dokman restart myproject

# Restart specific service
dokman restart myproject --service web

# Stop and remove containers
dokman down myproject

# Remove with volumes
dokman down myproject --volumes
```

### Ver registros

```bash
# View all logs
dokman logs myproject

# View specific service logs
dokman logs myproject --service web

# Follow logs in real-time
dokman logs myproject --follow

# Show last N lines
dokman logs myproject --tail 100
```

### Ejecutar comandos

```bash
# Run command in container
dokman exec myproject web ls -la

# Interactive shell
dokman exec myproject web sh --interactive
```

## Referencia de comandos

### Gestión de proyectos

| Comando | Descripción |
|---------|-------------|
| `list` | Lista todos los proyectos de Docker Compose |
| `info <project>` | Muestra información detallada del proyecto |
| `register <path>` | Registra un proyecto para seguimiento |
| `unregister <project>` | Elimina el proyecto del seguimiento |
| `up` | Inicia un proyecto (se registra automáticamente si es necesario) |

### Ciclo de vida de servicios

| Comando | Descripción |
|---------|-------------|
| `start <project>` | Inicia servicios en un proyecto |
| `stop <project>` | Detiene servicios en un proyecto |
| `restart <project>` | Reinicia servicios en un proyecto |
| `down <project>` | Detiene y elimina contenedores/redes |
| `redeploy <project>` | Vuelve a implementar con imágenes actualizadas |
| `scale <project> <service> <replicas>` | Escala un servicio |

### Depuración e inspección

| Comando | Descripción |
|---------|-------------|
| `logs <project>` | Muestra registros de servicios |
| `exec <project> <service> <command>` | Ejecuta comando en contenedor |
| `health <project>` | Muestra estado de verificación de salud |
| `events <project>` | Transmite eventos de Docker |
| `config <project>` | Muestra configuración compose resuelta |
| `env <project>` | Muestra variables de entorno |

### Gestión de recursos

| Comando | Descripción |
|---------|-------------|
| `images [project]` | Lista imágenes de Docker |
| `volumes [project]` | Lista volúmenes de Docker |
| `networks [project]` | Lista redes de Docker |
| `stats <project>` | Muestra estadísticas de uso de recursos |
| `pull <project>` | Descarga las últimas imágenes |
| `build <project>` | Construye imágenes desde el archivo compose |

## Opciones de comandos

### Opciones globales

- `--format, -f`: Formato de salida (`table` o `json`)
- `--help`: Muestra ayuda del comando

### Opciones comunes

- `--service, -s`: Apunta a un servicio específico
- `--all, -a`: Incluye todos los elementos (registrados y no registrados)
- `--volumes, -v`: Incluye volúmenes en la operación

### Opciones de registros

- `--follow, -f`: Transmite registros en tiempo real
- `--tail, -n`: Número de líneas a mostrar

### Opciones de reimplantación

- `--no-pull`: Omitir la descarga de las últimas imágenes
- `--strict`: Fallar si la descarga de cualquier imagen falla

### Opciones de compilación

- `--no-cache`: Compilar sin usar caché

### Opciones de estadísticas

- `--no-stream`: Mostrar un único instantáneo en lugar de transmitir

### Opciones de entorno

- `--show-secrets`: Mostrar valores sensibles (enmascarados por defecto)
- `--export`: Salida en formato de exportación de shell

## Códigos de salida

| Código | Significado |
|------|---------|
| 0 | Éxito |
| 1 | Error general |
| 2 | Proyecto no encontrado |
| 3 | Servicio no encontrado |
| 4 | Error de conexión con Docker |
| 5 | Error en el archivo compose |
| 6 | Operación fallida |

## Configuración

Dokman almacena su registro de proyectos en:

```
~/.config/dokman/projects.json
```

Este archivo rastrea los proyectos registrados y la ubicación de sus archivos compose.

## Arquitectura

Dokman sigue una arquitectura en capas:

```
CLI Layer (Typer) -> Service Layer -> Docker Client Layer -> Storage Layer
```

- Capa CLI: Comandos basados en Typer con formato de salida Rich
- Capa de Servicios: Lógica de negocio (ProjectManager, ServiceManager, ResourceManager)
- Capa de Cliente Docker: Envuelve SDK de Docker y comandos compose
- Capa de Almacenamiento: Registro de proyectos basado en JSON

## Desarrollo

### Configurar entorno de desarrollo

```bash
# Install with dev dependencies
uv sync --extra dev
```

### Ejecutar pruebas

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/properties/test_models_properties.py

# Run with verbose output
uv run pytest -v
```

### Calidad de código

```bash
# Lint code
uvx ruff check

# Type check
uvx ty check
```

### Estructura del proyecto

```
dokman/
  cli/           # CLI commands and output formatting
  clients/       # Docker SDK and compose command wrappers
  models/        # Data models (Project, Service, etc.)
  services/      # Business logic layer
  storage/       # Project registry persistence
tests/
  properties/    # Property-based tests (Hypothesis)
```

## Dependencias

- typer: Marco de trabajo CLI
- docker: SDK de Docker para Python
- rich: Formato de salida terminal

### Dependencias de desarrollo

- pytest: Marco de trabajo de pruebas
- hypothesis: Pruebas basadas en propiedades
- pytest-mock: Soporte de mocking

## Licencia

Licencia MIT

## Contribuir

1. Realice un fork del repositorio
2. Cree una rama de características
3. Realice sus cambios
4. Ejecute pruebas y linting
5. Envíe una pull request
