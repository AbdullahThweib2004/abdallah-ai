---
id: nawa-inference
type: project
title: "Nawa: Neural Network Inference Engine in C++"
language: en
status: approved
visibility: public
last_reviewed: 2026-11-16
tags: [cpp, machine-learning, performance, simd, quantization]
project_status: in_progress
technologies: [C++20, CMake, GoogleTest, Google Benchmark, AVX2, FMA, Python, PyTorch, HTML, CSS, JavaScript, GitHub Actions]
repository_url: https://github.com/AbdullahThweib2004/nawa-inference
demo_url: null
featured: true
order: 4
---
# Project: Nawa, a Neural Network Inference Engine

## Project ID
See frontmatter.

## Status
See frontmatter. Steps 1 to 9 are done (tensors through CPU optimization). Step 10, extensions, is next.

## One-line summary
A lightweight neural-network inference engine written from scratch in C++20, with no external math libraries, whose outputs match PyTorch and which runs MNIST digit classification from a command-line tool and a browser demo.

## Problem
A learning project: to understand what really happens when a trained neural network runs, by rebuilding the core of an inference engine from the ground up and then optimizing it for the CPU.

## Target users
Developers and students who want to see how inference engines work inside. It also demonstrates low-level performance engineering skills.

## Abdallah's contribution
Abdallah designed and built the whole project on his own. The name "Nawa" comes from the Arabic word نواة, meaning core or nucleus.

## Architecture
A model is trained in Python with PyTorch and exported to a custom Nawa model format. The C++ engine loads it and runs it with its own tensors, layers (Linear, ReLU, Sigmoid, Softmax, INT8 Linear), an AVX2 matrix-multiplication kernel, a thread pool and INT8 quantization. A command-line tool evaluates and predicts, and a small web demo served by the engine lets users draw a digit in the browser while preprocessing and inference run in C++.

## Technologies
See frontmatter.

## Data sources
The MNIST handwritten digit dataset.

## Key implementation details
- All math is hand-written in C++20, with no Eigen or BLAS. Python is only used for training and exporting weights.
- The runtime matches PyTorch's outputs with a maximum error below 1e-6.
- A cache-blocked AVX2/FMA matrix-multiplication micro-kernel, chosen at runtime so the portable build still runs everywhere.
- Zero-allocation inference with a fused Linear and ReLU step.
- A thread pool that gives bit-identical results for any number of threads.
- INT8 weight quantization that makes the model file four times smaller.
- MNIST-style preprocessing for user drawings: inverting, cropping, scaling and centering the digit.
- The web demo visualizes what the model sees, which hidden neurons fire, and the connections that push toward the answer.

## Challenges and trade-offs
- Without preprocessing, a dark-on-light "2" was classified as a 7 with 100% confidence, because the model had only seen light digits on a dark background. Preprocessing fixed it (2 at 99.4%).
- INT8 is faster for single images but slower for large batches on this CPU, because that would need VNNI instructions.
- Benchmarking on a laptop: CPU cycles were used as a more trustworthy measure than seconds.

## Results (only verified results)
Measured on an Intel i7-11370H laptop (4 cores, AVX2 and FMA):
- MNIST test accuracy: 97.15% (INT8: 97.14%).
- Matrix multiplication efficiency: from 1.6% to about 88% of one core's peak.
- Single-image latency (p50): from 134 µs to 7.4 µs (INT8: 4.5 µs).
- Batch-256 throughput: 390,079 images per second on one thread (63 times faster than the naive version), and 624,554 images per second on four threads (101 times faster).
- Heap allocations per prediction: from 65 to 0.
- Model file size: 407 KB, or 103 KB with INT8.

## Limitations
- Currently supports a small multilayer perceptron on MNIST. Planned extensions are not built yet.

## Public repository
See frontmatter.

## Demo URL
See frontmatter.

## Last reviewed
See frontmatter.
