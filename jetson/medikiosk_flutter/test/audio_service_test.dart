import 'dart:async';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_flutter/services/audio_service.dart';
import 'package:record/record.dart';

class TestPlayer implements AudioPlayer {
  final completion = StreamController<void>.broadcast();
  Completer<void>? stopping;
  bool failStop = false;
  int stops = 0;
  @override
  PlayerMode mode = PlayerMode.mediaPlayer;
  AudioContext? context;

  @override
  Stream<void> get onPlayerComplete => completion.stream;
  @override
  Future<void> play(Source source, {double? volume, double? balance,
      AudioContext? ctx, Duration? position, PlayerMode? mode}) async {
    this.mode = mode ?? PlayerMode.mediaPlayer;
  }
  @override
  Future<void> setAudioContext(AudioContext ctx) async { context = ctx; }
  @override
  Future<void> setPlaybackRate(double rate) async {}
  @override
  Future<void> stop() async {
    stops++;
    if (failStop) throw StateError('synthetic player failure');
    await stopping?.future;
  }
  @override
  Future<void> dispose() async { await completion.close(); }
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class TestRecorder implements AudioRecorder {
  @override
  Future<void> dispose() async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  test('timeout waits for native stop before releasing microphone', () async {
    final player = TestPlayer()..stopping = Completer<void>();
    final audio = AudioService(player: player, recorder: TestRecorder());
    var done = false;
    audio.playPcm(Uint8List(320), 16000).then((_) => done = true);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    expect(audio.isPlaying, isTrue);
    expect(player.mode, PlayerMode.mediaPlayer);
    expect(player.context!.android.audioFocus, AndroidAudioFocus.none);
    await Future<void>.delayed(const Duration(milliseconds: 2100));
    expect(player.stops, 1);
    expect(audio.isPlaying, isTrue);
    player.stopping!.complete();
    await Future<void>.delayed(const Duration(milliseconds: 10));
    await Future<void>.delayed(const Duration(milliseconds: 10));
    expect(done, isTrue);
    expect(audio.isPlaying, isFalse);
    audio.dispose();
  });

  test('failed native stop leaves capture blocked', () async {
    final player = TestPlayer()..failStop = true;
    final audio = AudioService(player: player, recorder: TestRecorder());
    var done = false;
    audio.playPcm(Uint8List(320), 16000).then((_) => done = true);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    await Future<void>.delayed(const Duration(milliseconds: 2100));
    await Future<void>.delayed(const Duration(milliseconds: 10));
    expect(done, isTrue);
    expect(audio.isPlaying, isTrue);
    expect(audio.status, contains('microphone remains paused'));
    audio.dispose();
  });

  test('normal native completion does not need a forced stop', () async {
    final player = TestPlayer();
    final audio = AudioService(player: player, recorder: TestRecorder());
    var done = false;
    audio.playPcm(Uint8List(320), 16000).then((_) => done = true);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    player.completion.add(null);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    await Future<void>.delayed(const Duration(milliseconds: 10));
    expect(done, isTrue);
    expect(audio.isPlaying, isFalse);
    expect(player.stops, 0);
    audio.dispose();
  });
}
