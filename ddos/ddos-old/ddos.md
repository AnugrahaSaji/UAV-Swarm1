# DDoS Detection & MAVLink Security System Analysis

## Overview
This document analyzes the current implementation of `tst1.py` which focuses on DDoS detection for MAVLink communications using Time Series Transformer (TST) models.

## Current System Architecture

### 1. DDoS Detection Module (`time_series_transformer()`)

#### Model Details
- **Model Type**: Time Series Transformer (TST)
- **Pre-trained Model**: `400_64_32_64_1_0.1_0.1_entire_model.pth`
- **Sequence Length**: 400 data points
- **Batch Size**: 4
- **Device**: CPU (map_location='cpu')

#### Data Processing
- **Input Features**:
  - `Mavlink_Count`: Number of MAVLink messages
  - `Total_length`: Total packet length
- **Target**: `Status` (normal/DDoS classification)
- **Preprocessing**: StandardScaler normalization
- **Data Source**: CSV files from `/home/dev/crypto/ddos/Preprocessing/Finaldata/`

#### Detection Process
1. Load pre-trained TST model
2. Read training data for scaler fitting
3. Process test data with normalization
4. Create time sequences (sliding window of 400 points)
5. Run continuous prediction loop
6. Measure prediction time performance

### 2. MAVLink Control Integration
- **Traffic Monitoring**: Analyzes MAVLink communication patterns
- **Feature Extraction**: Uses message counts and packet lengths
- **Anomaly Detection**: Identifies abnormal traffic patterns
- **Real-time Processing**: Continuous monitoring capability

### 3. Encryption Components (Currently Inactive)

#### Available Libraries
- **SPECK Cipher**: `Python_SPECK` from `crypto_dep.Speck.speck`
- **Crypto Utilities**: `pad`, `unpad` from `Crypto.Util.Padding`
- **Network**: `socket` for communication

#### Inactive Components
- Process 2 (`p2`): Commented out - likely another TST instance
- Process 3 (`p3`): Commented out - `speck_cryptography_proxy_algorithm`
- Actual encryption/decryption operations

## Current Execution Flow

### What Runs
1. **Single Process**: Only `p1` (time_series_transformer) executes
2. **Model Loading**: Loads TST model from disk
3. **Data Processing**: Processes test file `tcp_test_ddos_data_0.1.csv`
4. **Continuous Prediction**: Infinite loop measuring detection performance
5. **Performance Metrics**: Calculates average prediction time per record

### What Doesn't Run
1. **Encryption**: No data encryption/decryption
2. **Multiple Processes**: Only 1 of 3 planned processes active
3. **Network Communication**: Socket functionality unused
4. **Cryptographic Proxy**: Algorithm not implemented

## Technical Specifications

### Model Architecture
- **Input Dimension**: Single feature (Mavlink_Count)
- **Sequence Processing**: 400-point time windows
- **Classification**: Binary (normal/DDoS)
- **Inference Mode**: model.eval() for prediction

### Performance Monitoring
- **Timing**: Per-record prediction time measurement
- **Memory**: Memory profiler imported but not used
- **Metrics**: Classification report capabilities available

### Data Structure
```
/home/dev/crypto/ddos/
├── Preprocessing/
│   └── Finaldata/
│       ├── train_ddos_data_0.1.csv
│       └── tcp_test_ddos_data_0.1.csv
├── evaluation/
│   └── tst/
│       ├── models/
│       │   └── 400_64_32_64_1_0.1_0.1_entire_model.pth
│       └── results/
│           └── performance/
```

## Missing Implementations

### 1. Complete Encryption System
- SPECK cipher integration
- Data padding/unpadding
- Key management
- Encrypted communication channels

### 2. Multi-Process Architecture
- Process 2: Additional TST instance
- Process 3: Cryptographic proxy algorithm
- Inter-process communication

### 3. Network Communication
- Socket-based communication
- MAVLink message handling
- Encrypted data transmission

## Security Considerations

### Current Protection
- **DDoS Detection**: Real-time anomaly detection
- **Pattern Recognition**: Time series analysis
- **Continuous Monitoring**: Infinite loop execution

### Missing Protection
- **Data Encryption**: No confidentiality protection
- **Authentication**: No message authentication
- **Integrity**: No data integrity verification

## Performance Characteristics

### Current Metrics
- **Detection Speed**: Measured per-record prediction time
- **Model Size**: Pre-trained model loaded once
- **Memory Usage**: Single process execution

### Optimization Opportunities
- Multi-process parallel execution
- GPU acceleration (currently CPU-only)
- Batch processing optimization
- Memory usage profiling

## Future Enhancements

### Immediate Priorities
1. Implement SPECK encryption functionality
2. Activate multi-process architecture
3. Add network communication layer
4. Integrate cryptographic proxy algorithm

### Long-term Goals
1. Real-time MAVLink message encryption
2. Advanced threat detection algorithms
3. Performance optimization
4. Comprehensive security framework

## Conclusion
The current system provides a solid foundation for DDoS detection using Time Series Transformers but lacks the complete encryption and multi-process architecture needed for a comprehensive MAVLink security solution.

---

# Encryption Codebase Analysis

## Available Cryptographic Implementations

### 1. SPECK Cipher Implementation

#### Location & Structure
- **Primary Implementation**: `/home/dev/crypto/final_speck/drone_speck_proxy_final.py`
- **Library Path**: `crypto_dep.Speck.speck.Python_SPECK`
- **Key Features**: Lightweight block cipher designed for IoT/embedded systems

#### SPECK Proxy Configuration
```python
# Drone to GCS Communication (Encryption)
encrypt_target_host = "10.42.0.166"  # GCS IP
encrypt_target_port = 14550          # MAVLink port
listen_host_encrypt = "127.0.0.1"    # Local proxy
listen_port_encrypt = 5010           # Proxy port

# GCS to Drone Communication (Decryption)  
decrypt_target_host = "127.0.0.1"    # Local forwarding
decrypt_target_port = 14551          # Local MAVLink port
listen_host_decrypt = "10.42.0.34"   # Drone IP
listen_port_decrypt = 5002           # Proxy port

# Cryptographic Parameters
key = b"0123456789abcdef"  # 16-byte key
IV = b"0123456789abcdef"   # 16-byte initialization vector
```

#### SPECK Functions Available
- `encrypt_data(raw_data)`: Encrypts MAVLink packets with padding
- `decrypt_data(encrypted)`: Decrypts and unpads MAVLink packets
- `forward_encrypted(data, addr)`: Network forwarding (incomplete)

### 2. Camellia Cipher Implementation

#### Location & Structure
- **Implementation**: `/home/dev/crypto/final_camelia/drone_camelia_proxy_final.py`
- **Library**: `camellia.CamelliaCipher` with CBC mode
- **Standard**: ISO/IEC 18033-3 approved cipher

#### Camellia Configuration
```python
# Same network topology as SPECK
key = b'0123456789abcdef'  # 16-byte key
IV = b'0123456789abcdef'   # 16-byte IV
mode = camellia.MODE_CBC   # Cipher Block Chaining

# Encryption Function
cipher = camellia.CamelliaCipher(key=key, IV=IV, mode=camellia.MODE_CBC)
encrypted = cipher.encrypt(pad(raw_data, 16))
```

#### Camellia Features
- **Block Size**: 128 bits (16 bytes)
- **Key Sizes**: 128, 192, 256 bits supported
- **Modes**: ECB, CBC, CFB, OFB, CTR available
- **Security**: Approved by NESSIE and CRYPTREC

### 3. ASCON Cipher Implementation

#### Location & Structure
- **Implementation**: `/home/dev/crypto/final_ascon/drone_proxy_final_latency.py`
- **Library**: Custom ASCON implementation
- **Type**: Authenticated Encryption with Associated Data (AEAD)

#### ASCON Features
- **NIST LWC Winner**: Selected for lightweight cryptography standard
- **Variants**: Ascon-128, Ascon-128a, Ascon-80pq
- **Authentication**: Built-in integrity verification
- **Performance**: Optimized for IoT devices

#### ASCON Integration
```python
# MAVLink packet processing with timing
encrypted_data, addr = listen_socket.recvfrom(bufsize)
decrypted_data = decrypt_data(encrypted_data)
mav_temp = mavutil.mavlink.MAVLink(None)
parsed = mav_temp.parse_char(decrypted_data)
timestamp = datetime.now().microsecond
```

### 4. HIGHT Cipher Implementation

#### Location & Structure
- **Implementation**: `/home/dev/crypto/crypto_dep/HIGHT/`
- **Type**: Lightweight 64-bit block cipher
- **Key Size**: 128 bits
- **Target**: Ultra-low resource devices (RFID, sensors)

#### HIGHT Specifications
```python
# Core Functions Available
def hight_encryption(P, MK)    # 64-bit plaintext, 128-bit master key
def hight_decryption(C, MK)    # 64-bit ciphertext, 128-bit master key

# Mode Support
- ECB Mode: Electronic Codebook
- CBC Mode: Cipher Block Chaining  
- CFB Mode: Cipher Feedback

# Hardware Requirements
- Only 3048 gates on 0.25 μm technology
- Suitable for RFID tags and WSN sensors
```

#### HIGHT Test Vectors
- **Extensive validation** with known test vectors
- **Cross-verified** with reference implementations
- **Multiple modes** tested with different IV/key combinations

### 5. PrintCipher Implementation

#### Location & Structure  
- **Path**: `/home/dev/crypto/crypto_dep/PrintCipher/`
- **Type**: Ultra-lightweight block cipher
- **Block Size**: 48 or 96 bits
- **Key Size**: 80 or 128 bits

### 6. Additional Cryptographic Libraries

#### Comprehensive Crypto Dependencies
```
crypto_dep/
├── Speck/          # NSA-designed lightweight cipher
├── PrintCipher/    # Ultra-lightweight for printing/RFID
├── HIGHT/          # Korean lightweight standard
├── camellia/       # Japanese standard cipher
└── ascon/          # NIST LWC winner
```

## Network Proxy Architecture

### Bidirectional Communication Flow
```
Drone (RPi) ←→ Encryption Proxy ←→ GCS
    ↓              ↓                 ↓
127.0.0.1:14551 ← 10.42.0.34:5002 ← Network
    ↑              ↑                 ↑  
127.0.0.1:5010  → 10.42.0.166:14550 → Network
```

### Threading Architecture
- **Encrypt Thread**: Handles drone→GCS communication
- **Decrypt Thread**: Handles GCS→drone communication  
- **Concurrent Processing**: Simultaneous bidirectional encryption

### MAVLink Integration Points
```python
# Packet parsing and timing
mav_temp = mavutil.mavlink.MAVLink(None)
parsed_packet = mav_temp.parse_char(decrypted_data)
processing_time = datetime.now().microsecond
```

## Security Analysis by Algorithm

### Performance Characteristics
| Algorithm | Block Size | Key Size | Speed | Security Level |
|-----------|------------|----------|-------|----------------|
| SPECK     | 64/128-bit | 128-bit  | Fast  | NSA-designed   |
| Camellia  | 128-bit    | 128-bit  | Medium| ISO standard   |
| ASCON     | Stream     | 128-bit  | Fast  | NIST LWC       |
| HIGHT     | 64-bit     | 128-bit  | Fast  | Ultra-light    |

### Suitability for MAVLink
1. **ASCON**: Best choice - AEAD provides authentication
2. **Camellia**: Good security, standardized
3. **SPECK**: Fast but NSA-designed (controversy)
4. **HIGHT**: Very lightweight, good for resource-constrained

## Implementation Status

### Completed Components
- ✅ Multiple cipher implementations
- ✅ Proxy network architecture  
- ✅ Bidirectional communication setup
- ✅ MAVLink packet parsing
- ✅ Threading for concurrent processing

### Missing Components  
- ❌ Complete socket implementation in SPECK proxy
- ❌ Error handling and recovery
- ❌ Key management system
- ❌ Integration with DDoS detection
- ❌ Performance benchmarking across algorithms
- ❌ Secure key exchange protocols

### Code Quality Issues
1. **Hardcoded Keys**: All implementations use static keys
2. **No Key Rotation**: Keys never change
3. **Limited Error Handling**: Minimal exception management  
4. **No Logging**: Insufficient operational visibility
5. **Missing Authentication**: No mutual authentication

## Integration Opportunities

### DDoS Detection + Encryption
```python
# Potential integration points:
1. Encrypt MAVLink traffic before DDoS analysis
2. Use encryption metadata as DDoS features
3. Implement secure model updates
4. Add encrypted command channels
```

### Multi-Algorithm Support
- **Algorithm Negotiation**: Dynamic cipher selection
- **Performance Monitoring**: Real-time algorithm switching
- **Fallback Mechanisms**: Graceful degradation

## Recommendations

### Immediate Actions
1. **Complete SPECK proxy implementation**
2. **Implement proper key management** 
3. **Add comprehensive error handling**
4. **Integrate with DDoS detection system**

### Security Enhancements
1. **Replace hardcoded keys** with secure key exchange
2. **Add message authentication** (recommend ASCON)
3. **Implement key rotation** mechanisms
4. **Add replay attack protection**

### Performance Optimization
1. **Benchmark all algorithms** with MAVLink traffic
2. **Implement adaptive algorithm selection**
3. **Optimize for real-time constraints**
4. **Add hardware acceleration support**
