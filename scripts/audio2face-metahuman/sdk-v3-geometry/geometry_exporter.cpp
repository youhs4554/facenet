// SPDX-FileCopyrightText: Copyright (c) 2026
// SPDX-License-Identifier: MIT
// Thin exporter around NVIDIA's official Audio2Face-3D SDK executor APIs.

#include "audio2face/audio2face.h"
#include "audio2x/cuda_utils.h"
#include "audio2x/internal/audio2x.h"

#include <cuda_runtime_api.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

struct Destroyer {
  template <typename T> void operator()(T* value) const { value->Destroy(); }
};
template <typename T> using UniquePtr = std::unique_ptr<T, Destroyer>;

static void Check(std::error_code error, const char* operation) {
  if (error) throw std::runtime_error(std::string(operation) + ": " + error.message());
}

static std::vector<float> ReadPcm16MonoWav(const fs::path& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("cannot open input WAV");
  std::vector<char> bytes((std::istreambuf_iterator<char>(input)), {});
  if (bytes.size() < 44 || std::string(bytes.data(), 4) != "RIFF" ||
      std::string(bytes.data() + 8, 4) != "WAVE") {
    throw std::runtime_error("input is not a RIFF/WAVE file");
  }
  std::size_t offset = 12;
  std::uint16_t format = 0, channels = 0, bits = 0;
  std::uint32_t sampleRate = 0;
  const char* data = nullptr;
  std::size_t dataSize = 0;
  auto u16 = [&](std::size_t at) { std::uint16_t value; std::memcpy(&value, bytes.data()+at, 2); return value; };
  auto u32 = [&](std::size_t at) { std::uint32_t value; std::memcpy(&value, bytes.data()+at, 4); return value; };
  while (offset + 8 <= bytes.size()) {
    const std::string id(bytes.data() + offset, 4);
    const std::uint32_t size = u32(offset + 4);
    const std::size_t payload = offset + 8;
    if (payload + size > bytes.size()) throw std::runtime_error("invalid WAV chunk");
    if (id == "fmt ") {
      format = u16(payload); channels = u16(payload + 2);
      sampleRate = u32(payload + 4); bits = u16(payload + 14);
    } else if (id == "data") {
      data = bytes.data() + payload; dataSize = size;
    }
    offset = payload + size + (size & 1U);
  }
  if (format != 1 || channels != 1 || bits != 16 || sampleRate != 16000 || !data) {
    throw std::runtime_error("WAV must be PCM16 mono 16 kHz");
  }
  const auto* samples = reinterpret_cast<const std::int16_t*>(data);
  std::vector<float> result(dataSize / 2);
  std::transform(samples, samples + result.size(), result.begin(),
                 [](std::int16_t value) { return float(value) / 32768.0f; });
  return result;
}

static std::vector<std::string> Split(const std::string& value) {
  std::vector<std::string> result; std::stringstream stream(value); std::string item;
  while (std::getline(stream, item, ',')) result.push_back(item);
  return result;
}

using FaceParameters = std::map<std::string, float>;

static FaceParameters ReadFaceParameters(const fs::path& path) {
  std::ifstream input(path);
  if (!input) throw std::runtime_error("cannot open request configuration");
  FaceParameters result;
  std::string line;
  bool inFaceParameters = false;
  while (std::getline(input, line)) {
    if (line == "face_parameters:") { inFaceParameters = true; continue; }
    if (!inFaceParameters) continue;
    if (line.empty() || line[0] != ' ') break;
    const auto first = line.find_first_not_of(' ');
    const auto separator = line.find(':', first);
    if (first == std::string::npos || separator == std::string::npos) continue;
    const auto name = line.substr(first, separator - first);
    const auto value = line.substr(separator + 1);
    result[name] = std::stof(value);
  }
  if (result.empty()) throw std::runtime_error("request has no face_parameters mapping");
  return result;
}

static void ApplyFaceParameters(nva2f::IFaceExecutor& executor,
                                const FaceParameters& values) {
  const auto value = [&](const char* name, float fallback) {
    const auto found = values.find(name);
    return found == values.end() ? fallback : found->second;
  };
  float inputStrength = 1.0f;
  Check(nva2f::GetExecutorInputStrength(executor, inputStrength), "get input strength");
  Check(nva2f::SetExecutorInputStrength(
    executor, value("inputStrength", inputStrength)), "set input strength");

  nva2f::AnimatorSkinParams skin{};
  Check(nva2f::GetExecutorSkinParameters(executor, 0, skin), "get skin parameters");
  skin.lowerFaceSmoothing = value("lowerFaceSmoothing", skin.lowerFaceSmoothing);
  skin.upperFaceSmoothing = value("upperFaceSmoothing", skin.upperFaceSmoothing);
  skin.lowerFaceStrength = value("lowerFaceStrength", skin.lowerFaceStrength);
  skin.upperFaceStrength = value("upperFaceStrength", skin.upperFaceStrength);
  skin.faceMaskLevel = value("faceMaskLevel", skin.faceMaskLevel);
  skin.faceMaskSoftness = value("faceMaskSoftness", skin.faceMaskSoftness);
  skin.skinStrength = value("skinStrength", skin.skinStrength);
  skin.blinkStrength = value("blinkStrength", skin.blinkStrength);
  skin.eyelidOpenOffset = value("eyelidOpenOffset", skin.eyelidOpenOffset);
  skin.lipOpenOffset = value("lipOpenOffset", skin.lipOpenOffset);
  Check(nva2f::SetExecutorSkinParameters(executor, 0, skin), "set skin parameters");

  nva2f::AnimatorTongueParams tongue{};
  Check(nva2f::GetExecutorTongueParameters(executor, 0, tongue), "get tongue parameters");
  tongue.tongueStrength = value("tongueStrength", tongue.tongueStrength);
  tongue.tongueHeightOffset = value("tongueHeightOffset", tongue.tongueHeightOffset);
  tongue.tongueDepthOffset = value("tongueDepthOffset", tongue.tongueDepthOffset);
  Check(nva2f::SetExecutorTongueParameters(executor, 0, tongue), "set tongue parameters");
}

struct EmotionRow { std::int64_t timestamp; std::vector<float> values; };
static std::vector<EmotionRow> ReadEmotions(const fs::path& path) {
  std::ifstream input(path); std::string line;
  if (!std::getline(input, line)) throw std::runtime_error("emotion CSV is empty");
  const auto header = Split(line);
  const std::vector<std::string> order = {
    "amazement", "anger", "cheekiness", "disgust", "fear",
    "grief", "joy", "outofbreath", "pain", "sadness"};
  std::map<std::string, std::size_t> columns;
  std::size_t timeColumn = 0;
  for (std::size_t index = 0; index < header.size(); ++index) {
    if (header[index] == "time_code") timeColumn = index;
    const auto marker = header[index].find("emotion_values.");
    if (marker != std::string::npos) columns[header[index].substr(marker + 15)] = index;
  }
  std::vector<EmotionRow> result;
  while (std::getline(input, line)) {
    const auto values = Split(line); if (values.size() != header.size()) continue;
    EmotionRow row; row.timestamp = std::llround(std::stod(values[timeColumn]));
    for (const auto& name : order) row.values.push_back(std::stof(values.at(columns.at(name))));
    result.push_back(std::move(row));
  }
  if (result.empty()) throw std::runtime_error("emotion CSV has no records");
  return result;
}

template <typename Bundle>
static void AccumulateInputs(Bundle& bundle, const std::vector<float>& audio,
                             const std::vector<EmotionRow>& emotions) {
  auto& stream = bundle.GetCudaStream();
  auto& emotion = bundle.GetEmotionAccumulator(0);
  for (const auto& row : emotions) {
    Check(emotion.Accumulate(
      row.timestamp,
      nva2x::HostTensorFloatConstView{row.values.data(), row.values.size()},
      stream.Data()), "emotion accumulate");
  }
  Check(emotion.Close(), "emotion close");
  auto& audioAccumulator = bundle.GetAudioAccumulator(0);
  Check(audioAccumulator.Accumulate(
    nva2x::HostTensorFloatConstView{audio.data(), audio.size()},
    stream.Data()), "audio accumulate");
  Check(audioAccumulator.Close(), "audio close");
}

struct GeometryOutput {
  fs::path directory;
  std::ofstream skin, tongue, jaw, eyes, timestamps;
  std::size_t frames = 0, skinSize = 0, tongueSize = 0, jawSize = 0, eyesSize = 0;
  explicit GeometryOutput(const fs::path& dir) : directory(dir),
    skin(dir/"skin.f32", std::ios::binary), tongue(dir/"tongue.f32", std::ios::binary),
    jaw(dir/"jaw.f32", std::ios::binary), eyes(dir/"eyes.f32", std::ios::binary),
    timestamps(dir/"timestamps.csv") { timestamps << "frame,timestamp_current,timestamp_next\n"; }
};

static void CopyResult(std::ofstream& out, nva2x::DeviceTensorFloatConstView source,
                       cudaStream_t stream) {
  std::vector<float> host(source.Size());
  if (!host.empty()) {
    Check(nva2x::CopyDeviceToHost({host.data(), host.size()}, source, stream), "device to host");
    if (cudaStreamSynchronize(stream) != cudaSuccess) throw std::runtime_error("CUDA stream sync failed");
    if (!std::all_of(host.begin(), host.end(), [](float value) { return std::isfinite(value); }))
      throw std::runtime_error("non-finite geometry output");
    out.write(reinterpret_cast<const char*>(host.data()), host.size()*sizeof(float));
  }
}

static int RunGeometry(const fs::path& model, const std::vector<float>& audio,
                       const std::vector<EmotionRow>& emotions,
                       const FaceParameters& faceParameters,
                       const fs::path& outdir) {
  constexpr std::size_t identityIndex = 0;
  constexpr bool constantNoise = true;
  UniquePtr<nva2f::IGeometryExecutorBundle> bundle(
    nva2f::ReadDiffusionGeometryExecutorBundle(
      1, model.c_str(), nva2f::IGeometryExecutor::ExecutionOption::All,
      identityIndex, constantNoise, nullptr));
  if (!bundle) throw std::runtime_error("failed to create diffusion geometry bundle");
  ApplyFaceParameters(bundle->GetExecutor(), faceParameters);
  GeometryOutput output(outdir);
  auto callback = [](void* userdata, const nva2f::IGeometryExecutor::Results& results) {
    auto& out = *static_cast<GeometryOutput*>(userdata);
    if (out.frames == 0) {
      out.skinSize=results.skinGeometry.Size(); out.tongueSize=results.tongueGeometry.Size();
      out.jawSize=results.jawTransform.Size(); out.eyesSize=results.eyesRotation.Size();
    }
    CopyResult(out.skin, results.skinGeometry, results.skinCudaStream);
    CopyResult(out.tongue, results.tongueGeometry, results.tongueCudaStream);
    CopyResult(out.jaw, results.jawTransform, results.jawCudaStream);
    CopyResult(out.eyes, results.eyesRotation, results.eyesCudaStream);
    out.timestamps << out.frames << ',' << results.timeStampCurrentFrame << ',' << results.timeStampNextFrame << '\n';
    ++out.frames; return true;
  };
  Check(bundle->GetExecutor().SetResultsCallback(callback, &output), "set geometry callback");
  AccumulateInputs(*bundle, audio, emotions);
  while (nva2x::GetNbReadyTracks(bundle->GetExecutor()) > 0)
    Check(bundle->GetExecutor().Execute(nullptr), "geometry execute");
  std::ofstream meta(outdir/"geometry-metadata.json");
  meta << "{\n  \"schema_version\": 1,\n  \"model\": \"Audio2Face-3D-v3.0 multi_v3.2\",\n"
       << "  \"identity_index\": " << identityIndex << ",\n  \"constant_noise\": true,\n"
       << "  \"request_face_parameters_applied\": true,\n"
       << "  \"execution_option\": \"All\",\n  \"frame_count\": " << output.frames << ",\n"
       << "  \"skin_size\": " << output.skinSize << ",\n  \"tongue_size\": " << output.tongueSize << ",\n"
       << "  \"jaw_size\": " << output.jawSize << ",\n  \"eyes_size\": " << output.eyesSize << "\n}\n";
  return 0;
}

struct WeightOutput { std::ofstream weights, timestamps; std::size_t frames=0, count=0; explicit WeightOutput(const fs::path& d):weights(d/"weights.f32",std::ios::binary),timestamps(d/"weights-timestamps.csv"){timestamps<<"frame,timestamp_current,timestamp_next\n";} };
static int RunWeights(const fs::path& model, const std::vector<float>& audio,
                      const std::vector<EmotionRow>& emotions,
                      const FaceParameters& faceParameters,
                      const fs::path& outdir) {
  constexpr std::size_t identityIndex = 0;
  constexpr bool constantNoise = true;
  constexpr bool useGpuSolver = true;
  UniquePtr<nva2f::IBlendshapeExecutorBundle> bundle(
    nva2f::ReadDiffusionBlendshapeSolveExecutorBundle(
      1, model.c_str(), nva2f::IGeometryExecutor::ExecutionOption::SkinTongue,
      useGpuSolver, identityIndex, constantNoise, nullptr, nullptr));
  if (!bundle) throw std::runtime_error("failed to create diffusion blendshape bundle");
  ApplyFaceParameters(bundle->GetExecutor(), faceParameters);
  WeightOutput output(outdir);
  auto callback=[](void* userdata,const nva2f::IBlendshapeExecutor::DeviceResults& results){auto& out=*static_cast<WeightOutput*>(userdata); out.count=results.weights.Size(); CopyResult(out.weights,results.weights,results.cudaStream); out.timestamps<<out.frames<<','<<results.timeStampCurrentFrame<<','<<results.timeStampNextFrame<<'\n'; ++out.frames; return true;};
  Check(bundle->GetExecutor().SetResultsCallback(callback,&output),"set weights callback");
  AccumulateInputs(*bundle,audio,emotions);
  while(nva2x::GetNbReadyTracks(bundle->GetExecutor())>0) Check(bundle->GetExecutor().Execute(nullptr),"weights execute");
  Check(bundle->GetExecutor().Wait(0),"weights wait");
  std::ofstream meta(outdir/"weights-metadata.json"); meta<<"{\n  \"schema_version\": 1,\n  \"frame_count\": "<<output.frames<<",\n  \"weight_count\": "<<output.count<<",\n  \"identity_index\": "<<identityIndex<<",\n  \"constant_noise\": true,\n  \"solver_backend\": \"gpu\",\n  \"request_face_parameters_applied\": true\n}\n";
  return 0;
}

int main(int argc, char** argv) {
  if (argc == 2 && std::string(argv[1]) == "--help") { std::cout << "usage: a2f-geometry-exporter MODE MODEL_JSON AUDIO_WAV EMOTION_CSV REQUEST_YAML OUTPUT_DIR\n"; return 0; }
  if (argc != 7) { std::cerr << "invalid arguments\n"; return 2; }
  try {
    Check(nva2x::SetCudaDeviceIfNeeded(0), "select CUDA device");
    const std::string mode=argv[1]; const fs::path outdir=argv[6]; fs::create_directories(outdir);
    const auto audio=ReadPcm16MonoWav(argv[3]); const auto emotions=ReadEmotions(argv[4]);
    const auto faceParameters=ReadFaceParameters(argv[5]);
    if(mode=="geometry") return RunGeometry(argv[2],audio,emotions,faceParameters,outdir);
    if(mode=="weights") return RunWeights(argv[2],audio,emotions,faceParameters,outdir);
    throw std::runtime_error("mode must be geometry or weights");
  } catch(const std::exception& error) { std::cerr<<"ERROR: "<<error.what()<<'\n'; return 1; }
}
