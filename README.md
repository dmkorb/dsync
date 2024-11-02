# DSync - File Synchronization Service

DSync is a robust file synchronization service built in Python that allows you to efficiently monitor and synchronize files across different locations.

## 🚀 Features

- Real-time file monitoring and synchronization
- YAML-based configuration
- Progress tracking for file operations
- Cross-platform compatibility
- Command-line interface

## 📋 Requirements

- Python 3.8 or higher
- Poetry for dependency management

## 🛠️ Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/dsync.git
cd dsync
```

2. Install Poetry (if not already installed):
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

3. Install dependencies:
```bash
poetry install
```

## ⚙️ Configuration

Create a `config.yaml` file in your project directory:

```yaml
source:
  path: "/path/to/source"
  
destination:
  path: "/path/to/destination"

options:
  ignore_patterns:
    - "*.tmp"
    - "*.log"
  sync_interval: 60  # seconds
```

## 🚦 Usage

After installation, you can use the `dsync` command-line tool:

```bash
# Start synchronization service
dsync start

# Check status
dsync status

# Stop synchronization
dsync stop
```

## 🧪 Development

### Running Tests

```bash
poetry run pytest
```

### Code Formatting

```bash
# Format code with Black
poetry run black .

# Check code style with Flake8
poetry run flake8
```

## 📦 Project Structure

```
dsync/
├── sync_service/
│   ├── cli/
│   │   └── main.py
│   ├── core/
│   └── utils/
├── tests/
├── config.yaml
├── pyproject.toml
└── README.md
```

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🛣️ Roadmap

- [ ] Add support for multiple sync pairs
- [ ] Implement encryption for secure file transfer
- [ ] Add web interface for monitoring
- [ ] Support for cloud storage providers
- [ ] Add conflict resolution strategies
- [ ] Implement bandwidth throttling
- [ ] Add support for symbolic links

## ⚠️ Known Issues

- None reported yet

## 📚 Documentation

For detailed documentation, please visit our [Wiki](https://github.com/yourusername/dsync/wiki).

## 🙏 Acknowledgments

- [Watchdog](https://github.com/gorakhargosh/watchdog) for file system events monitoring
- [PyYAML](https://pyyaml.org/) for configuration file parsing
- [tqdm](https://github.com/tqdm/tqdm) for progress bar functionality


