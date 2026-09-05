// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'database.dart';

// ignore_for_file: type=lint
class $DraftsTable extends Drafts with TableInfo<$DraftsTable, Draft> {
  @override
  final GeneratedDatabase attachedDatabase;
  final String? _alias;
  $DraftsTable(this.attachedDatabase, [this._alias]);
  static const VerificationMeta _intakeIdMeta =
      const VerificationMeta('intakeId');
  @override
  late final GeneratedColumn<String> intakeId = GeneratedColumn<String>(
      'intake_id', aliasedName, false,
      type: DriftSqlType.string, requiredDuringInsert: true);
  static const VerificationMeta _hospitalIdMeta =
      const VerificationMeta('hospitalId');
  @override
  late final GeneratedColumn<String> hospitalId = GeneratedColumn<String>(
      'hospital_id', aliasedName, false,
      type: DriftSqlType.string, requiredDuringInsert: true);
  static const VerificationMeta _hospitalNameMeta =
      const VerificationMeta('hospitalName');
  @override
  late final GeneratedColumn<String> hospitalName = GeneratedColumn<String>(
      'hospital_name', aliasedName, true,
      type: DriftSqlType.string, requiredDuringInsert: false);
  static const VerificationMeta _departmentCodeMeta =
      const VerificationMeta('departmentCode');
  @override
  late final GeneratedColumn<String> departmentCode = GeneratedColumn<String>(
      'department_code', aliasedName, true,
      type: DriftSqlType.string, requiredDuringInsert: false);
  static const VerificationMeta _languageMeta =
      const VerificationMeta('language');
  @override
  late final GeneratedColumn<String> language = GeneratedColumn<String>(
      'language', aliasedName, false,
      type: DriftSqlType.string, requiredDuringInsert: true);
  static const VerificationMeta _reporterMeta =
      const VerificationMeta('reporter');
  @override
  late final GeneratedColumn<String> reporter = GeneratedColumn<String>(
      'reporter', aliasedName, false,
      type: DriftSqlType.string, requiredDuringInsert: true);
  static const VerificationMeta _answersJsonMeta =
      const VerificationMeta('answersJson');
  @override
  late final GeneratedColumn<String> answersJson = GeneratedColumn<String>(
      'answers_json', aliasedName, false,
      type: DriftSqlType.string, requiredDuringInsert: true);
  static const VerificationMeta _contentVersionMeta =
      const VerificationMeta('contentVersion');
  @override
  late final GeneratedColumn<String> contentVersion = GeneratedColumn<String>(
      'content_version', aliasedName, false,
      type: DriftSqlType.string, requiredDuringInsert: true);
  static const VerificationMeta _returnVisitMeta =
      const VerificationMeta('returnVisit');
  @override
  late final GeneratedColumn<bool> returnVisit = GeneratedColumn<bool>(
      'return_visit', aliasedName, false,
      type: DriftSqlType.bool,
      requiredDuringInsert: false,
      defaultConstraints: GeneratedColumn.constraintIsAlways(
          'CHECK ("return_visit" IN (0, 1))'),
      defaultValue: const Constant(false));
  static const VerificationMeta _startedAtMeta =
      const VerificationMeta('startedAt');
  @override
  late final GeneratedColumn<DateTime> startedAt = GeneratedColumn<DateTime>(
      'started_at', aliasedName, false,
      type: DriftSqlType.dateTime, requiredDuringInsert: true);
  static const VerificationMeta _updatedAtMeta =
      const VerificationMeta('updatedAt');
  @override
  late final GeneratedColumn<DateTime> updatedAt = GeneratedColumn<DateTime>(
      'updated_at', aliasedName, false,
      type: DriftSqlType.dateTime, requiredDuringInsert: true);
  static const VerificationMeta _queuedPayloadMeta =
      const VerificationMeta('queuedPayload');
  @override
  late final GeneratedColumn<String> queuedPayload = GeneratedColumn<String>(
      'queued_payload', aliasedName, true,
      type: DriftSqlType.string, requiredDuringInsert: false);
  static const VerificationMeta _idempotencyKeyMeta =
      const VerificationMeta('idempotencyKey');
  @override
  late final GeneratedColumn<String> idempotencyKey = GeneratedColumn<String>(
      'idempotency_key', aliasedName, false,
      type: DriftSqlType.string, requiredDuringInsert: true);
  @override
  List<GeneratedColumn> get $columns => [
        intakeId,
        hospitalId,
        hospitalName,
        departmentCode,
        language,
        reporter,
        answersJson,
        contentVersion,
        returnVisit,
        startedAt,
        updatedAt,
        queuedPayload,
        idempotencyKey
      ];
  @override
  String get aliasedName => _alias ?? actualTableName;
  @override
  String get actualTableName => $name;
  static const String $name = 'drafts';
  @override
  VerificationContext validateIntegrity(Insertable<Draft> instance,
      {bool isInserting = false}) {
    final context = VerificationContext();
    final data = instance.toColumns(true);
    if (data.containsKey('intake_id')) {
      context.handle(_intakeIdMeta,
          intakeId.isAcceptableOrUnknown(data['intake_id']!, _intakeIdMeta));
    } else if (isInserting) {
      context.missing(_intakeIdMeta);
    }
    if (data.containsKey('hospital_id')) {
      context.handle(
          _hospitalIdMeta,
          hospitalId.isAcceptableOrUnknown(
              data['hospital_id']!, _hospitalIdMeta));
    } else if (isInserting) {
      context.missing(_hospitalIdMeta);
    }
    if (data.containsKey('hospital_name')) {
      context.handle(
          _hospitalNameMeta,
          hospitalName.isAcceptableOrUnknown(
              data['hospital_name']!, _hospitalNameMeta));
    }
    if (data.containsKey('department_code')) {
      context.handle(
          _departmentCodeMeta,
          departmentCode.isAcceptableOrUnknown(
              data['department_code']!, _departmentCodeMeta));
    }
    if (data.containsKey('language')) {
      context.handle(_languageMeta,
          language.isAcceptableOrUnknown(data['language']!, _languageMeta));
    } else if (isInserting) {
      context.missing(_languageMeta);
    }
    if (data.containsKey('reporter')) {
      context.handle(_reporterMeta,
          reporter.isAcceptableOrUnknown(data['reporter']!, _reporterMeta));
    } else if (isInserting) {
      context.missing(_reporterMeta);
    }
    if (data.containsKey('answers_json')) {
      context.handle(
          _answersJsonMeta,
          answersJson.isAcceptableOrUnknown(
              data['answers_json']!, _answersJsonMeta));
    } else if (isInserting) {
      context.missing(_answersJsonMeta);
    }
    if (data.containsKey('content_version')) {
      context.handle(
          _contentVersionMeta,
          contentVersion.isAcceptableOrUnknown(
              data['content_version']!, _contentVersionMeta));
    } else if (isInserting) {
      context.missing(_contentVersionMeta);
    }
    if (data.containsKey('return_visit')) {
      context.handle(
          _returnVisitMeta,
          returnVisit.isAcceptableOrUnknown(
              data['return_visit']!, _returnVisitMeta));
    }
    if (data.containsKey('started_at')) {
      context.handle(_startedAtMeta,
          startedAt.isAcceptableOrUnknown(data['started_at']!, _startedAtMeta));
    } else if (isInserting) {
      context.missing(_startedAtMeta);
    }
    if (data.containsKey('updated_at')) {
      context.handle(_updatedAtMeta,
          updatedAt.isAcceptableOrUnknown(data['updated_at']!, _updatedAtMeta));
    } else if (isInserting) {
      context.missing(_updatedAtMeta);
    }
    if (data.containsKey('queued_payload')) {
      context.handle(
          _queuedPayloadMeta,
          queuedPayload.isAcceptableOrUnknown(
              data['queued_payload']!, _queuedPayloadMeta));
    }
    if (data.containsKey('idempotency_key')) {
      context.handle(
          _idempotencyKeyMeta,
          idempotencyKey.isAcceptableOrUnknown(
              data['idempotency_key']!, _idempotencyKeyMeta));
    } else if (isInserting) {
      context.missing(_idempotencyKeyMeta);
    }
    return context;
  }

  @override
  Set<GeneratedColumn> get $primaryKey => {intakeId};
  @override
  Draft map(Map<String, dynamic> data, {String? tablePrefix}) {
    final effectivePrefix = tablePrefix != null ? '$tablePrefix.' : '';
    return Draft(
      intakeId: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}intake_id'])!,
      hospitalId: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}hospital_id'])!,
      hospitalName: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}hospital_name']),
      departmentCode: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}department_code']),
      language: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}language'])!,
      reporter: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}reporter'])!,
      answersJson: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}answers_json'])!,
      contentVersion: attachedDatabase.typeMapping.read(
          DriftSqlType.string, data['${effectivePrefix}content_version'])!,
      returnVisit: attachedDatabase.typeMapping
          .read(DriftSqlType.bool, data['${effectivePrefix}return_visit'])!,
      startedAt: attachedDatabase.typeMapping
          .read(DriftSqlType.dateTime, data['${effectivePrefix}started_at'])!,
      updatedAt: attachedDatabase.typeMapping
          .read(DriftSqlType.dateTime, data['${effectivePrefix}updated_at'])!,
      queuedPayload: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}queued_payload']),
      idempotencyKey: attachedDatabase.typeMapping.read(
          DriftSqlType.string, data['${effectivePrefix}idempotency_key'])!,
    );
  }

  @override
  $DraftsTable createAlias(String alias) {
    return $DraftsTable(attachedDatabase, alias);
  }
}

class Draft extends DataClass implements Insertable<Draft> {
  final String intakeId;
  final String hospitalId;

  /// The hospital's display name, carried so a receipt written days later by
  /// the background queue can name the hospital the patient chose rather than
  /// its id. Nullable because drafts written before this column existed have
  /// none, and a resumed draft is worth more than a tidy schema.
  final String? hospitalName;
  final String? departmentCode;
  final String language;
  final String reporter;

  /// The answers so far, as JSON. Opaque to the database on purpose: the schema
  /// of an answer is the bundle's business, and a column per field would need a
  /// migration every time a clinician edits a pathway.
  final String answersJson;
  final String contentVersion;

  /// Whether this hospital had seen the patient before when the intake started
  /// — §5 screen 8. Stored rather than re-derived, because a resumed intake
  /// must keep the plan it began with: re-deciding it would change which
  /// questions remain halfway through.
  final bool returnVisit;
  final DateTime startedAt;
  final DateTime updatedAt;

  /// Set once the record has been assembled and is waiting to go out.
  final String? queuedPayload;

  /// Generated once per intake, not per attempt — §9. A key per attempt would
  /// make every retry a new intake.
  final String idempotencyKey;
  const Draft(
      {required this.intakeId,
      required this.hospitalId,
      this.hospitalName,
      this.departmentCode,
      required this.language,
      required this.reporter,
      required this.answersJson,
      required this.contentVersion,
      required this.returnVisit,
      required this.startedAt,
      required this.updatedAt,
      this.queuedPayload,
      required this.idempotencyKey});
  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    map['intake_id'] = Variable<String>(intakeId);
    map['hospital_id'] = Variable<String>(hospitalId);
    if (!nullToAbsent || hospitalName != null) {
      map['hospital_name'] = Variable<String>(hospitalName);
    }
    if (!nullToAbsent || departmentCode != null) {
      map['department_code'] = Variable<String>(departmentCode);
    }
    map['language'] = Variable<String>(language);
    map['reporter'] = Variable<String>(reporter);
    map['answers_json'] = Variable<String>(answersJson);
    map['content_version'] = Variable<String>(contentVersion);
    map['return_visit'] = Variable<bool>(returnVisit);
    map['started_at'] = Variable<DateTime>(startedAt);
    map['updated_at'] = Variable<DateTime>(updatedAt);
    if (!nullToAbsent || queuedPayload != null) {
      map['queued_payload'] = Variable<String>(queuedPayload);
    }
    map['idempotency_key'] = Variable<String>(idempotencyKey);
    return map;
  }

  DraftsCompanion toCompanion(bool nullToAbsent) {
    return DraftsCompanion(
      intakeId: Value(intakeId),
      hospitalId: Value(hospitalId),
      hospitalName: hospitalName == null && nullToAbsent
          ? const Value.absent()
          : Value(hospitalName),
      departmentCode: departmentCode == null && nullToAbsent
          ? const Value.absent()
          : Value(departmentCode),
      language: Value(language),
      reporter: Value(reporter),
      answersJson: Value(answersJson),
      contentVersion: Value(contentVersion),
      returnVisit: Value(returnVisit),
      startedAt: Value(startedAt),
      updatedAt: Value(updatedAt),
      queuedPayload: queuedPayload == null && nullToAbsent
          ? const Value.absent()
          : Value(queuedPayload),
      idempotencyKey: Value(idempotencyKey),
    );
  }

  factory Draft.fromJson(Map<String, dynamic> json,
      {ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return Draft(
      intakeId: serializer.fromJson<String>(json['intakeId']),
      hospitalId: serializer.fromJson<String>(json['hospitalId']),
      hospitalName: serializer.fromJson<String?>(json['hospitalName']),
      departmentCode: serializer.fromJson<String?>(json['departmentCode']),
      language: serializer.fromJson<String>(json['language']),
      reporter: serializer.fromJson<String>(json['reporter']),
      answersJson: serializer.fromJson<String>(json['answersJson']),
      contentVersion: serializer.fromJson<String>(json['contentVersion']),
      returnVisit: serializer.fromJson<bool>(json['returnVisit']),
      startedAt: serializer.fromJson<DateTime>(json['startedAt']),
      updatedAt: serializer.fromJson<DateTime>(json['updatedAt']),
      queuedPayload: serializer.fromJson<String?>(json['queuedPayload']),
      idempotencyKey: serializer.fromJson<String>(json['idempotencyKey']),
    );
  }
  @override
  Map<String, dynamic> toJson({ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return <String, dynamic>{
      'intakeId': serializer.toJson<String>(intakeId),
      'hospitalId': serializer.toJson<String>(hospitalId),
      'hospitalName': serializer.toJson<String?>(hospitalName),
      'departmentCode': serializer.toJson<String?>(departmentCode),
      'language': serializer.toJson<String>(language),
      'reporter': serializer.toJson<String>(reporter),
      'answersJson': serializer.toJson<String>(answersJson),
      'contentVersion': serializer.toJson<String>(contentVersion),
      'returnVisit': serializer.toJson<bool>(returnVisit),
      'startedAt': serializer.toJson<DateTime>(startedAt),
      'updatedAt': serializer.toJson<DateTime>(updatedAt),
      'queuedPayload': serializer.toJson<String?>(queuedPayload),
      'idempotencyKey': serializer.toJson<String>(idempotencyKey),
    };
  }

  Draft copyWith(
          {String? intakeId,
          String? hospitalId,
          Value<String?> hospitalName = const Value.absent(),
          Value<String?> departmentCode = const Value.absent(),
          String? language,
          String? reporter,
          String? answersJson,
          String? contentVersion,
          bool? returnVisit,
          DateTime? startedAt,
          DateTime? updatedAt,
          Value<String?> queuedPayload = const Value.absent(),
          String? idempotencyKey}) =>
      Draft(
        intakeId: intakeId ?? this.intakeId,
        hospitalId: hospitalId ?? this.hospitalId,
        hospitalName:
            hospitalName.present ? hospitalName.value : this.hospitalName,
        departmentCode:
            departmentCode.present ? departmentCode.value : this.departmentCode,
        language: language ?? this.language,
        reporter: reporter ?? this.reporter,
        answersJson: answersJson ?? this.answersJson,
        contentVersion: contentVersion ?? this.contentVersion,
        returnVisit: returnVisit ?? this.returnVisit,
        startedAt: startedAt ?? this.startedAt,
        updatedAt: updatedAt ?? this.updatedAt,
        queuedPayload:
            queuedPayload.present ? queuedPayload.value : this.queuedPayload,
        idempotencyKey: idempotencyKey ?? this.idempotencyKey,
      );
  Draft copyWithCompanion(DraftsCompanion data) {
    return Draft(
      intakeId: data.intakeId.present ? data.intakeId.value : this.intakeId,
      hospitalId:
          data.hospitalId.present ? data.hospitalId.value : this.hospitalId,
      hospitalName: data.hospitalName.present
          ? data.hospitalName.value
          : this.hospitalName,
      departmentCode: data.departmentCode.present
          ? data.departmentCode.value
          : this.departmentCode,
      language: data.language.present ? data.language.value : this.language,
      reporter: data.reporter.present ? data.reporter.value : this.reporter,
      answersJson:
          data.answersJson.present ? data.answersJson.value : this.answersJson,
      contentVersion: data.contentVersion.present
          ? data.contentVersion.value
          : this.contentVersion,
      returnVisit:
          data.returnVisit.present ? data.returnVisit.value : this.returnVisit,
      startedAt: data.startedAt.present ? data.startedAt.value : this.startedAt,
      updatedAt: data.updatedAt.present ? data.updatedAt.value : this.updatedAt,
      queuedPayload: data.queuedPayload.present
          ? data.queuedPayload.value
          : this.queuedPayload,
      idempotencyKey: data.idempotencyKey.present
          ? data.idempotencyKey.value
          : this.idempotencyKey,
    );
  }

  @override
  String toString() {
    return (StringBuffer('Draft(')
          ..write('intakeId: $intakeId, ')
          ..write('hospitalId: $hospitalId, ')
          ..write('hospitalName: $hospitalName, ')
          ..write('departmentCode: $departmentCode, ')
          ..write('language: $language, ')
          ..write('reporter: $reporter, ')
          ..write('answersJson: $answersJson, ')
          ..write('contentVersion: $contentVersion, ')
          ..write('returnVisit: $returnVisit, ')
          ..write('startedAt: $startedAt, ')
          ..write('updatedAt: $updatedAt, ')
          ..write('queuedPayload: $queuedPayload, ')
          ..write('idempotencyKey: $idempotencyKey')
          ..write(')'))
        .toString();
  }

  @override
  int get hashCode => Object.hash(
      intakeId,
      hospitalId,
      hospitalName,
      departmentCode,
      language,
      reporter,
      answersJson,
      contentVersion,
      returnVisit,
      startedAt,
      updatedAt,
      queuedPayload,
      idempotencyKey);
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is Draft &&
          other.intakeId == this.intakeId &&
          other.hospitalId == this.hospitalId &&
          other.hospitalName == this.hospitalName &&
          other.departmentCode == this.departmentCode &&
          other.language == this.language &&
          other.reporter == this.reporter &&
          other.answersJson == this.answersJson &&
          other.contentVersion == this.contentVersion &&
          other.returnVisit == this.returnVisit &&
          other.startedAt == this.startedAt &&
          other.updatedAt == this.updatedAt &&
          other.queuedPayload == this.queuedPayload &&
          other.idempotencyKey == this.idempotencyKey);
}

class DraftsCompanion extends UpdateCompanion<Draft> {
  final Value<String> intakeId;
  final Value<String> hospitalId;
  final Value<String?> hospitalName;
  final Value<String?> departmentCode;
  final Value<String> language;
  final Value<String> reporter;
  final Value<String> answersJson;
  final Value<String> contentVersion;
  final Value<bool> returnVisit;
  final Value<DateTime> startedAt;
  final Value<DateTime> updatedAt;
  final Value<String?> queuedPayload;
  final Value<String> idempotencyKey;
  final Value<int> rowid;
  const DraftsCompanion({
    this.intakeId = const Value.absent(),
    this.hospitalId = const Value.absent(),
    this.hospitalName = const Value.absent(),
    this.departmentCode = const Value.absent(),
    this.language = const Value.absent(),
    this.reporter = const Value.absent(),
    this.answersJson = const Value.absent(),
    this.contentVersion = const Value.absent(),
    this.returnVisit = const Value.absent(),
    this.startedAt = const Value.absent(),
    this.updatedAt = const Value.absent(),
    this.queuedPayload = const Value.absent(),
    this.idempotencyKey = const Value.absent(),
    this.rowid = const Value.absent(),
  });
  DraftsCompanion.insert({
    required String intakeId,
    required String hospitalId,
    this.hospitalName = const Value.absent(),
    this.departmentCode = const Value.absent(),
    required String language,
    required String reporter,
    required String answersJson,
    required String contentVersion,
    this.returnVisit = const Value.absent(),
    required DateTime startedAt,
    required DateTime updatedAt,
    this.queuedPayload = const Value.absent(),
    required String idempotencyKey,
    this.rowid = const Value.absent(),
  })  : intakeId = Value(intakeId),
        hospitalId = Value(hospitalId),
        language = Value(language),
        reporter = Value(reporter),
        answersJson = Value(answersJson),
        contentVersion = Value(contentVersion),
        startedAt = Value(startedAt),
        updatedAt = Value(updatedAt),
        idempotencyKey = Value(idempotencyKey);
  static Insertable<Draft> custom({
    Expression<String>? intakeId,
    Expression<String>? hospitalId,
    Expression<String>? hospitalName,
    Expression<String>? departmentCode,
    Expression<String>? language,
    Expression<String>? reporter,
    Expression<String>? answersJson,
    Expression<String>? contentVersion,
    Expression<bool>? returnVisit,
    Expression<DateTime>? startedAt,
    Expression<DateTime>? updatedAt,
    Expression<String>? queuedPayload,
    Expression<String>? idempotencyKey,
    Expression<int>? rowid,
  }) {
    return RawValuesInsertable({
      if (intakeId != null) 'intake_id': intakeId,
      if (hospitalId != null) 'hospital_id': hospitalId,
      if (hospitalName != null) 'hospital_name': hospitalName,
      if (departmentCode != null) 'department_code': departmentCode,
      if (language != null) 'language': language,
      if (reporter != null) 'reporter': reporter,
      if (answersJson != null) 'answers_json': answersJson,
      if (contentVersion != null) 'content_version': contentVersion,
      if (returnVisit != null) 'return_visit': returnVisit,
      if (startedAt != null) 'started_at': startedAt,
      if (updatedAt != null) 'updated_at': updatedAt,
      if (queuedPayload != null) 'queued_payload': queuedPayload,
      if (idempotencyKey != null) 'idempotency_key': idempotencyKey,
      if (rowid != null) 'rowid': rowid,
    });
  }

  DraftsCompanion copyWith(
      {Value<String>? intakeId,
      Value<String>? hospitalId,
      Value<String?>? hospitalName,
      Value<String?>? departmentCode,
      Value<String>? language,
      Value<String>? reporter,
      Value<String>? answersJson,
      Value<String>? contentVersion,
      Value<bool>? returnVisit,
      Value<DateTime>? startedAt,
      Value<DateTime>? updatedAt,
      Value<String?>? queuedPayload,
      Value<String>? idempotencyKey,
      Value<int>? rowid}) {
    return DraftsCompanion(
      intakeId: intakeId ?? this.intakeId,
      hospitalId: hospitalId ?? this.hospitalId,
      hospitalName: hospitalName ?? this.hospitalName,
      departmentCode: departmentCode ?? this.departmentCode,
      language: language ?? this.language,
      reporter: reporter ?? this.reporter,
      answersJson: answersJson ?? this.answersJson,
      contentVersion: contentVersion ?? this.contentVersion,
      returnVisit: returnVisit ?? this.returnVisit,
      startedAt: startedAt ?? this.startedAt,
      updatedAt: updatedAt ?? this.updatedAt,
      queuedPayload: queuedPayload ?? this.queuedPayload,
      idempotencyKey: idempotencyKey ?? this.idempotencyKey,
      rowid: rowid ?? this.rowid,
    );
  }

  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    if (intakeId.present) {
      map['intake_id'] = Variable<String>(intakeId.value);
    }
    if (hospitalId.present) {
      map['hospital_id'] = Variable<String>(hospitalId.value);
    }
    if (hospitalName.present) {
      map['hospital_name'] = Variable<String>(hospitalName.value);
    }
    if (departmentCode.present) {
      map['department_code'] = Variable<String>(departmentCode.value);
    }
    if (language.present) {
      map['language'] = Variable<String>(language.value);
    }
    if (reporter.present) {
      map['reporter'] = Variable<String>(reporter.value);
    }
    if (answersJson.present) {
      map['answers_json'] = Variable<String>(answersJson.value);
    }
    if (contentVersion.present) {
      map['content_version'] = Variable<String>(contentVersion.value);
    }
    if (returnVisit.present) {
      map['return_visit'] = Variable<bool>(returnVisit.value);
    }
    if (startedAt.present) {
      map['started_at'] = Variable<DateTime>(startedAt.value);
    }
    if (updatedAt.present) {
      map['updated_at'] = Variable<DateTime>(updatedAt.value);
    }
    if (queuedPayload.present) {
      map['queued_payload'] = Variable<String>(queuedPayload.value);
    }
    if (idempotencyKey.present) {
      map['idempotency_key'] = Variable<String>(idempotencyKey.value);
    }
    if (rowid.present) {
      map['rowid'] = Variable<int>(rowid.value);
    }
    return map;
  }

  @override
  String toString() {
    return (StringBuffer('DraftsCompanion(')
          ..write('intakeId: $intakeId, ')
          ..write('hospitalId: $hospitalId, ')
          ..write('hospitalName: $hospitalName, ')
          ..write('departmentCode: $departmentCode, ')
          ..write('language: $language, ')
          ..write('reporter: $reporter, ')
          ..write('answersJson: $answersJson, ')
          ..write('contentVersion: $contentVersion, ')
          ..write('returnVisit: $returnVisit, ')
          ..write('startedAt: $startedAt, ')
          ..write('updatedAt: $updatedAt, ')
          ..write('queuedPayload: $queuedPayload, ')
          ..write('idempotencyKey: $idempotencyKey, ')
          ..write('rowid: $rowid')
          ..write(')'))
        .toString();
  }
}

class $PendingDocumentsTable extends PendingDocuments
    with TableInfo<$PendingDocumentsTable, PendingDocument> {
  @override
  final GeneratedDatabase attachedDatabase;
  final String? _alias;
  $PendingDocumentsTable(this.attachedDatabase, [this._alias]);
  static const VerificationMeta _documentIdMeta =
      const VerificationMeta('documentId');
  @override
  late final GeneratedColumn<String> documentId = GeneratedColumn<String>(
      'document_id', aliasedName, false,
      type: DriftSqlType.string, requiredDuringInsert: true);
  static const VerificationMeta _intakeIdMeta =
      const VerificationMeta('intakeId');
  @override
  late final GeneratedColumn<String> intakeId = GeneratedColumn<String>(
      'intake_id', aliasedName, false,
      type: DriftSqlType.string, requiredDuringInsert: true);
  static const VerificationMeta _filePathMeta =
      const VerificationMeta('filePath');
  @override
  late final GeneratedColumn<String> filePath = GeneratedColumn<String>(
      'file_path', aliasedName, false,
      type: DriftSqlType.string, requiredDuringInsert: true);
  static const VerificationMeta _kindMeta = const VerificationMeta('kind');
  @override
  late final GeneratedColumn<String> kind = GeneratedColumn<String>(
      'kind', aliasedName, false,
      type: DriftSqlType.string,
      requiredDuringInsert: false,
      defaultValue: const Constant('other'));
  static const VerificationMeta _statusMeta = const VerificationMeta('status');
  @override
  late final GeneratedColumn<String> status = GeneratedColumn<String>(
      'status', aliasedName, false,
      type: DriftSqlType.string,
      requiredDuringInsert: false,
      defaultValue: const Constant('pending'));
  static const VerificationMeta _attemptsMeta =
      const VerificationMeta('attempts');
  @override
  late final GeneratedColumn<int> attempts = GeneratedColumn<int>(
      'attempts', aliasedName, false,
      type: DriftSqlType.int,
      requiredDuringInsert: false,
      defaultValue: const Constant(0));
  static const VerificationMeta _capturedAtMeta =
      const VerificationMeta('capturedAt');
  @override
  late final GeneratedColumn<DateTime> capturedAt = GeneratedColumn<DateTime>(
      'captured_at', aliasedName, false,
      type: DriftSqlType.dateTime, requiredDuringInsert: true);
  @override
  List<GeneratedColumn> get $columns =>
      [documentId, intakeId, filePath, kind, status, attempts, capturedAt];
  @override
  String get aliasedName => _alias ?? actualTableName;
  @override
  String get actualTableName => $name;
  static const String $name = 'pending_documents';
  @override
  VerificationContext validateIntegrity(Insertable<PendingDocument> instance,
      {bool isInserting = false}) {
    final context = VerificationContext();
    final data = instance.toColumns(true);
    if (data.containsKey('document_id')) {
      context.handle(
          _documentIdMeta,
          documentId.isAcceptableOrUnknown(
              data['document_id']!, _documentIdMeta));
    } else if (isInserting) {
      context.missing(_documentIdMeta);
    }
    if (data.containsKey('intake_id')) {
      context.handle(_intakeIdMeta,
          intakeId.isAcceptableOrUnknown(data['intake_id']!, _intakeIdMeta));
    } else if (isInserting) {
      context.missing(_intakeIdMeta);
    }
    if (data.containsKey('file_path')) {
      context.handle(_filePathMeta,
          filePath.isAcceptableOrUnknown(data['file_path']!, _filePathMeta));
    } else if (isInserting) {
      context.missing(_filePathMeta);
    }
    if (data.containsKey('kind')) {
      context.handle(
          _kindMeta, kind.isAcceptableOrUnknown(data['kind']!, _kindMeta));
    }
    if (data.containsKey('status')) {
      context.handle(_statusMeta,
          status.isAcceptableOrUnknown(data['status']!, _statusMeta));
    }
    if (data.containsKey('attempts')) {
      context.handle(_attemptsMeta,
          attempts.isAcceptableOrUnknown(data['attempts']!, _attemptsMeta));
    }
    if (data.containsKey('captured_at')) {
      context.handle(
          _capturedAtMeta,
          capturedAt.isAcceptableOrUnknown(
              data['captured_at']!, _capturedAtMeta));
    } else if (isInserting) {
      context.missing(_capturedAtMeta);
    }
    return context;
  }

  @override
  Set<GeneratedColumn> get $primaryKey => {documentId};
  @override
  PendingDocument map(Map<String, dynamic> data, {String? tablePrefix}) {
    final effectivePrefix = tablePrefix != null ? '$tablePrefix.' : '';
    return PendingDocument(
      documentId: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}document_id'])!,
      intakeId: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}intake_id'])!,
      filePath: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}file_path'])!,
      kind: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}kind'])!,
      status: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}status'])!,
      attempts: attachedDatabase.typeMapping
          .read(DriftSqlType.int, data['${effectivePrefix}attempts'])!,
      capturedAt: attachedDatabase.typeMapping
          .read(DriftSqlType.dateTime, data['${effectivePrefix}captured_at'])!,
    );
  }

  @override
  $PendingDocumentsTable createAlias(String alias) {
    return $PendingDocumentsTable(attachedDatabase, alias);
  }
}

class PendingDocument extends DataClass implements Insertable<PendingDocument> {
  final String documentId;
  final String intakeId;

  /// Path on disk. The bytes are not in the database: a 500 KB JPEG per row
  /// would make the encrypted database large and slow to open, and the file
  /// is deleted alongside the row.
  final String filePath;
  final String kind;
  final String status;
  final int attempts;
  final DateTime capturedAt;
  const PendingDocument(
      {required this.documentId,
      required this.intakeId,
      required this.filePath,
      required this.kind,
      required this.status,
      required this.attempts,
      required this.capturedAt});
  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    map['document_id'] = Variable<String>(documentId);
    map['intake_id'] = Variable<String>(intakeId);
    map['file_path'] = Variable<String>(filePath);
    map['kind'] = Variable<String>(kind);
    map['status'] = Variable<String>(status);
    map['attempts'] = Variable<int>(attempts);
    map['captured_at'] = Variable<DateTime>(capturedAt);
    return map;
  }

  PendingDocumentsCompanion toCompanion(bool nullToAbsent) {
    return PendingDocumentsCompanion(
      documentId: Value(documentId),
      intakeId: Value(intakeId),
      filePath: Value(filePath),
      kind: Value(kind),
      status: Value(status),
      attempts: Value(attempts),
      capturedAt: Value(capturedAt),
    );
  }

  factory PendingDocument.fromJson(Map<String, dynamic> json,
      {ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return PendingDocument(
      documentId: serializer.fromJson<String>(json['documentId']),
      intakeId: serializer.fromJson<String>(json['intakeId']),
      filePath: serializer.fromJson<String>(json['filePath']),
      kind: serializer.fromJson<String>(json['kind']),
      status: serializer.fromJson<String>(json['status']),
      attempts: serializer.fromJson<int>(json['attempts']),
      capturedAt: serializer.fromJson<DateTime>(json['capturedAt']),
    );
  }
  @override
  Map<String, dynamic> toJson({ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return <String, dynamic>{
      'documentId': serializer.toJson<String>(documentId),
      'intakeId': serializer.toJson<String>(intakeId),
      'filePath': serializer.toJson<String>(filePath),
      'kind': serializer.toJson<String>(kind),
      'status': serializer.toJson<String>(status),
      'attempts': serializer.toJson<int>(attempts),
      'capturedAt': serializer.toJson<DateTime>(capturedAt),
    };
  }

  PendingDocument copyWith(
          {String? documentId,
          String? intakeId,
          String? filePath,
          String? kind,
          String? status,
          int? attempts,
          DateTime? capturedAt}) =>
      PendingDocument(
        documentId: documentId ?? this.documentId,
        intakeId: intakeId ?? this.intakeId,
        filePath: filePath ?? this.filePath,
        kind: kind ?? this.kind,
        status: status ?? this.status,
        attempts: attempts ?? this.attempts,
        capturedAt: capturedAt ?? this.capturedAt,
      );
  PendingDocument copyWithCompanion(PendingDocumentsCompanion data) {
    return PendingDocument(
      documentId:
          data.documentId.present ? data.documentId.value : this.documentId,
      intakeId: data.intakeId.present ? data.intakeId.value : this.intakeId,
      filePath: data.filePath.present ? data.filePath.value : this.filePath,
      kind: data.kind.present ? data.kind.value : this.kind,
      status: data.status.present ? data.status.value : this.status,
      attempts: data.attempts.present ? data.attempts.value : this.attempts,
      capturedAt:
          data.capturedAt.present ? data.capturedAt.value : this.capturedAt,
    );
  }

  @override
  String toString() {
    return (StringBuffer('PendingDocument(')
          ..write('documentId: $documentId, ')
          ..write('intakeId: $intakeId, ')
          ..write('filePath: $filePath, ')
          ..write('kind: $kind, ')
          ..write('status: $status, ')
          ..write('attempts: $attempts, ')
          ..write('capturedAt: $capturedAt')
          ..write(')'))
        .toString();
  }

  @override
  int get hashCode => Object.hash(
      documentId, intakeId, filePath, kind, status, attempts, capturedAt);
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is PendingDocument &&
          other.documentId == this.documentId &&
          other.intakeId == this.intakeId &&
          other.filePath == this.filePath &&
          other.kind == this.kind &&
          other.status == this.status &&
          other.attempts == this.attempts &&
          other.capturedAt == this.capturedAt);
}

class PendingDocumentsCompanion extends UpdateCompanion<PendingDocument> {
  final Value<String> documentId;
  final Value<String> intakeId;
  final Value<String> filePath;
  final Value<String> kind;
  final Value<String> status;
  final Value<int> attempts;
  final Value<DateTime> capturedAt;
  final Value<int> rowid;
  const PendingDocumentsCompanion({
    this.documentId = const Value.absent(),
    this.intakeId = const Value.absent(),
    this.filePath = const Value.absent(),
    this.kind = const Value.absent(),
    this.status = const Value.absent(),
    this.attempts = const Value.absent(),
    this.capturedAt = const Value.absent(),
    this.rowid = const Value.absent(),
  });
  PendingDocumentsCompanion.insert({
    required String documentId,
    required String intakeId,
    required String filePath,
    this.kind = const Value.absent(),
    this.status = const Value.absent(),
    this.attempts = const Value.absent(),
    required DateTime capturedAt,
    this.rowid = const Value.absent(),
  })  : documentId = Value(documentId),
        intakeId = Value(intakeId),
        filePath = Value(filePath),
        capturedAt = Value(capturedAt);
  static Insertable<PendingDocument> custom({
    Expression<String>? documentId,
    Expression<String>? intakeId,
    Expression<String>? filePath,
    Expression<String>? kind,
    Expression<String>? status,
    Expression<int>? attempts,
    Expression<DateTime>? capturedAt,
    Expression<int>? rowid,
  }) {
    return RawValuesInsertable({
      if (documentId != null) 'document_id': documentId,
      if (intakeId != null) 'intake_id': intakeId,
      if (filePath != null) 'file_path': filePath,
      if (kind != null) 'kind': kind,
      if (status != null) 'status': status,
      if (attempts != null) 'attempts': attempts,
      if (capturedAt != null) 'captured_at': capturedAt,
      if (rowid != null) 'rowid': rowid,
    });
  }

  PendingDocumentsCompanion copyWith(
      {Value<String>? documentId,
      Value<String>? intakeId,
      Value<String>? filePath,
      Value<String>? kind,
      Value<String>? status,
      Value<int>? attempts,
      Value<DateTime>? capturedAt,
      Value<int>? rowid}) {
    return PendingDocumentsCompanion(
      documentId: documentId ?? this.documentId,
      intakeId: intakeId ?? this.intakeId,
      filePath: filePath ?? this.filePath,
      kind: kind ?? this.kind,
      status: status ?? this.status,
      attempts: attempts ?? this.attempts,
      capturedAt: capturedAt ?? this.capturedAt,
      rowid: rowid ?? this.rowid,
    );
  }

  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    if (documentId.present) {
      map['document_id'] = Variable<String>(documentId.value);
    }
    if (intakeId.present) {
      map['intake_id'] = Variable<String>(intakeId.value);
    }
    if (filePath.present) {
      map['file_path'] = Variable<String>(filePath.value);
    }
    if (kind.present) {
      map['kind'] = Variable<String>(kind.value);
    }
    if (status.present) {
      map['status'] = Variable<String>(status.value);
    }
    if (attempts.present) {
      map['attempts'] = Variable<int>(attempts.value);
    }
    if (capturedAt.present) {
      map['captured_at'] = Variable<DateTime>(capturedAt.value);
    }
    if (rowid.present) {
      map['rowid'] = Variable<int>(rowid.value);
    }
    return map;
  }

  @override
  String toString() {
    return (StringBuffer('PendingDocumentsCompanion(')
          ..write('documentId: $documentId, ')
          ..write('intakeId: $intakeId, ')
          ..write('filePath: $filePath, ')
          ..write('kind: $kind, ')
          ..write('status: $status, ')
          ..write('attempts: $attempts, ')
          ..write('capturedAt: $capturedAt, ')
          ..write('rowid: $rowid')
          ..write(')'))
        .toString();
  }
}

class $ReceiptsTable extends Receipts with TableInfo<$ReceiptsTable, Receipt> {
  @override
  final GeneratedDatabase attachedDatabase;
  final String? _alias;
  $ReceiptsTable(this.attachedDatabase, [this._alias]);
  static const VerificationMeta _intakeIdMeta =
      const VerificationMeta('intakeId');
  @override
  late final GeneratedColumn<String> intakeId = GeneratedColumn<String>(
      'intake_id', aliasedName, false,
      type: DriftSqlType.string, requiredDuringInsert: true);
  static const VerificationMeta _referenceCodeMeta =
      const VerificationMeta('referenceCode');
  @override
  late final GeneratedColumn<String> referenceCode = GeneratedColumn<String>(
      'reference_code', aliasedName, false,
      type: DriftSqlType.string, requiredDuringInsert: true);
  static const VerificationMeta _hospitalNameMeta =
      const VerificationMeta('hospitalName');
  @override
  late final GeneratedColumn<String> hospitalName = GeneratedColumn<String>(
      'hospital_name', aliasedName, false,
      type: DriftSqlType.string, requiredDuringInsert: true);
  static const VerificationMeta _submittedAtMeta =
      const VerificationMeta('submittedAt');
  @override
  late final GeneratedColumn<DateTime> submittedAt = GeneratedColumn<DateTime>(
      'submitted_at', aliasedName, false,
      type: DriftSqlType.dateTime, requiredDuringInsert: true);
  @override
  List<GeneratedColumn> get $columns =>
      [intakeId, referenceCode, hospitalName, submittedAt];
  @override
  String get aliasedName => _alias ?? actualTableName;
  @override
  String get actualTableName => $name;
  static const String $name = 'receipts';
  @override
  VerificationContext validateIntegrity(Insertable<Receipt> instance,
      {bool isInserting = false}) {
    final context = VerificationContext();
    final data = instance.toColumns(true);
    if (data.containsKey('intake_id')) {
      context.handle(_intakeIdMeta,
          intakeId.isAcceptableOrUnknown(data['intake_id']!, _intakeIdMeta));
    } else if (isInserting) {
      context.missing(_intakeIdMeta);
    }
    if (data.containsKey('reference_code')) {
      context.handle(
          _referenceCodeMeta,
          referenceCode.isAcceptableOrUnknown(
              data['reference_code']!, _referenceCodeMeta));
    } else if (isInserting) {
      context.missing(_referenceCodeMeta);
    }
    if (data.containsKey('hospital_name')) {
      context.handle(
          _hospitalNameMeta,
          hospitalName.isAcceptableOrUnknown(
              data['hospital_name']!, _hospitalNameMeta));
    } else if (isInserting) {
      context.missing(_hospitalNameMeta);
    }
    if (data.containsKey('submitted_at')) {
      context.handle(
          _submittedAtMeta,
          submittedAt.isAcceptableOrUnknown(
              data['submitted_at']!, _submittedAtMeta));
    } else if (isInserting) {
      context.missing(_submittedAtMeta);
    }
    return context;
  }

  @override
  Set<GeneratedColumn> get $primaryKey => {intakeId};
  @override
  Receipt map(Map<String, dynamic> data, {String? tablePrefix}) {
    final effectivePrefix = tablePrefix != null ? '$tablePrefix.' : '';
    return Receipt(
      intakeId: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}intake_id'])!,
      referenceCode: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}reference_code'])!,
      hospitalName: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}hospital_name'])!,
      submittedAt: attachedDatabase.typeMapping
          .read(DriftSqlType.dateTime, data['${effectivePrefix}submitted_at'])!,
    );
  }

  @override
  $ReceiptsTable createAlias(String alias) {
    return $ReceiptsTable(attachedDatabase, alias);
  }
}

class Receipt extends DataClass implements Insertable<Receipt> {
  final String intakeId;
  final String referenceCode;
  final String hospitalName;
  final DateTime submittedAt;
  const Receipt(
      {required this.intakeId,
      required this.referenceCode,
      required this.hospitalName,
      required this.submittedAt});
  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    map['intake_id'] = Variable<String>(intakeId);
    map['reference_code'] = Variable<String>(referenceCode);
    map['hospital_name'] = Variable<String>(hospitalName);
    map['submitted_at'] = Variable<DateTime>(submittedAt);
    return map;
  }

  ReceiptsCompanion toCompanion(bool nullToAbsent) {
    return ReceiptsCompanion(
      intakeId: Value(intakeId),
      referenceCode: Value(referenceCode),
      hospitalName: Value(hospitalName),
      submittedAt: Value(submittedAt),
    );
  }

  factory Receipt.fromJson(Map<String, dynamic> json,
      {ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return Receipt(
      intakeId: serializer.fromJson<String>(json['intakeId']),
      referenceCode: serializer.fromJson<String>(json['referenceCode']),
      hospitalName: serializer.fromJson<String>(json['hospitalName']),
      submittedAt: serializer.fromJson<DateTime>(json['submittedAt']),
    );
  }
  @override
  Map<String, dynamic> toJson({ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return <String, dynamic>{
      'intakeId': serializer.toJson<String>(intakeId),
      'referenceCode': serializer.toJson<String>(referenceCode),
      'hospitalName': serializer.toJson<String>(hospitalName),
      'submittedAt': serializer.toJson<DateTime>(submittedAt),
    };
  }

  Receipt copyWith(
          {String? intakeId,
          String? referenceCode,
          String? hospitalName,
          DateTime? submittedAt}) =>
      Receipt(
        intakeId: intakeId ?? this.intakeId,
        referenceCode: referenceCode ?? this.referenceCode,
        hospitalName: hospitalName ?? this.hospitalName,
        submittedAt: submittedAt ?? this.submittedAt,
      );
  Receipt copyWithCompanion(ReceiptsCompanion data) {
    return Receipt(
      intakeId: data.intakeId.present ? data.intakeId.value : this.intakeId,
      referenceCode: data.referenceCode.present
          ? data.referenceCode.value
          : this.referenceCode,
      hospitalName: data.hospitalName.present
          ? data.hospitalName.value
          : this.hospitalName,
      submittedAt:
          data.submittedAt.present ? data.submittedAt.value : this.submittedAt,
    );
  }

  @override
  String toString() {
    return (StringBuffer('Receipt(')
          ..write('intakeId: $intakeId, ')
          ..write('referenceCode: $referenceCode, ')
          ..write('hospitalName: $hospitalName, ')
          ..write('submittedAt: $submittedAt')
          ..write(')'))
        .toString();
  }

  @override
  int get hashCode =>
      Object.hash(intakeId, referenceCode, hospitalName, submittedAt);
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is Receipt &&
          other.intakeId == this.intakeId &&
          other.referenceCode == this.referenceCode &&
          other.hospitalName == this.hospitalName &&
          other.submittedAt == this.submittedAt);
}

class ReceiptsCompanion extends UpdateCompanion<Receipt> {
  final Value<String> intakeId;
  final Value<String> referenceCode;
  final Value<String> hospitalName;
  final Value<DateTime> submittedAt;
  final Value<int> rowid;
  const ReceiptsCompanion({
    this.intakeId = const Value.absent(),
    this.referenceCode = const Value.absent(),
    this.hospitalName = const Value.absent(),
    this.submittedAt = const Value.absent(),
    this.rowid = const Value.absent(),
  });
  ReceiptsCompanion.insert({
    required String intakeId,
    required String referenceCode,
    required String hospitalName,
    required DateTime submittedAt,
    this.rowid = const Value.absent(),
  })  : intakeId = Value(intakeId),
        referenceCode = Value(referenceCode),
        hospitalName = Value(hospitalName),
        submittedAt = Value(submittedAt);
  static Insertable<Receipt> custom({
    Expression<String>? intakeId,
    Expression<String>? referenceCode,
    Expression<String>? hospitalName,
    Expression<DateTime>? submittedAt,
    Expression<int>? rowid,
  }) {
    return RawValuesInsertable({
      if (intakeId != null) 'intake_id': intakeId,
      if (referenceCode != null) 'reference_code': referenceCode,
      if (hospitalName != null) 'hospital_name': hospitalName,
      if (submittedAt != null) 'submitted_at': submittedAt,
      if (rowid != null) 'rowid': rowid,
    });
  }

  ReceiptsCompanion copyWith(
      {Value<String>? intakeId,
      Value<String>? referenceCode,
      Value<String>? hospitalName,
      Value<DateTime>? submittedAt,
      Value<int>? rowid}) {
    return ReceiptsCompanion(
      intakeId: intakeId ?? this.intakeId,
      referenceCode: referenceCode ?? this.referenceCode,
      hospitalName: hospitalName ?? this.hospitalName,
      submittedAt: submittedAt ?? this.submittedAt,
      rowid: rowid ?? this.rowid,
    );
  }

  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    if (intakeId.present) {
      map['intake_id'] = Variable<String>(intakeId.value);
    }
    if (referenceCode.present) {
      map['reference_code'] = Variable<String>(referenceCode.value);
    }
    if (hospitalName.present) {
      map['hospital_name'] = Variable<String>(hospitalName.value);
    }
    if (submittedAt.present) {
      map['submitted_at'] = Variable<DateTime>(submittedAt.value);
    }
    if (rowid.present) {
      map['rowid'] = Variable<int>(rowid.value);
    }
    return map;
  }

  @override
  String toString() {
    return (StringBuffer('ReceiptsCompanion(')
          ..write('intakeId: $intakeId, ')
          ..write('referenceCode: $referenceCode, ')
          ..write('hospitalName: $hospitalName, ')
          ..write('submittedAt: $submittedAt, ')
          ..write('rowid: $rowid')
          ..write(')'))
        .toString();
  }
}

abstract class _$LocalDatabase extends GeneratedDatabase {
  _$LocalDatabase(QueryExecutor e) : super(e);
  $LocalDatabaseManager get managers => $LocalDatabaseManager(this);
  late final $DraftsTable drafts = $DraftsTable(this);
  late final $PendingDocumentsTable pendingDocuments =
      $PendingDocumentsTable(this);
  late final $ReceiptsTable receipts = $ReceiptsTable(this);
  @override
  Iterable<TableInfo<Table, Object?>> get allTables =>
      allSchemaEntities.whereType<TableInfo<Table, Object?>>();
  @override
  List<DatabaseSchemaEntity> get allSchemaEntities =>
      [drafts, pendingDocuments, receipts];
}

typedef $$DraftsTableCreateCompanionBuilder = DraftsCompanion Function({
  required String intakeId,
  required String hospitalId,
  Value<String?> hospitalName,
  Value<String?> departmentCode,
  required String language,
  required String reporter,
  required String answersJson,
  required String contentVersion,
  Value<bool> returnVisit,
  required DateTime startedAt,
  required DateTime updatedAt,
  Value<String?> queuedPayload,
  required String idempotencyKey,
  Value<int> rowid,
});
typedef $$DraftsTableUpdateCompanionBuilder = DraftsCompanion Function({
  Value<String> intakeId,
  Value<String> hospitalId,
  Value<String?> hospitalName,
  Value<String?> departmentCode,
  Value<String> language,
  Value<String> reporter,
  Value<String> answersJson,
  Value<String> contentVersion,
  Value<bool> returnVisit,
  Value<DateTime> startedAt,
  Value<DateTime> updatedAt,
  Value<String?> queuedPayload,
  Value<String> idempotencyKey,
  Value<int> rowid,
});

class $$DraftsTableFilterComposer
    extends Composer<_$LocalDatabase, $DraftsTable> {
  $$DraftsTableFilterComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnFilters<String> get intakeId => $composableBuilder(
      column: $table.intakeId, builder: (column) => ColumnFilters(column));

  ColumnFilters<String> get hospitalId => $composableBuilder(
      column: $table.hospitalId, builder: (column) => ColumnFilters(column));

  ColumnFilters<String> get hospitalName => $composableBuilder(
      column: $table.hospitalName, builder: (column) => ColumnFilters(column));

  ColumnFilters<String> get departmentCode => $composableBuilder(
      column: $table.departmentCode,
      builder: (column) => ColumnFilters(column));

  ColumnFilters<String> get language => $composableBuilder(
      column: $table.language, builder: (column) => ColumnFilters(column));

  ColumnFilters<String> get reporter => $composableBuilder(
      column: $table.reporter, builder: (column) => ColumnFilters(column));

  ColumnFilters<String> get answersJson => $composableBuilder(
      column: $table.answersJson, builder: (column) => ColumnFilters(column));

  ColumnFilters<String> get contentVersion => $composableBuilder(
      column: $table.contentVersion,
      builder: (column) => ColumnFilters(column));

  ColumnFilters<bool> get returnVisit => $composableBuilder(
      column: $table.returnVisit, builder: (column) => ColumnFilters(column));

  ColumnFilters<DateTime> get startedAt => $composableBuilder(
      column: $table.startedAt, builder: (column) => ColumnFilters(column));

  ColumnFilters<DateTime> get updatedAt => $composableBuilder(
      column: $table.updatedAt, builder: (column) => ColumnFilters(column));

  ColumnFilters<String> get queuedPayload => $composableBuilder(
      column: $table.queuedPayload, builder: (column) => ColumnFilters(column));

  ColumnFilters<String> get idempotencyKey => $composableBuilder(
      column: $table.idempotencyKey,
      builder: (column) => ColumnFilters(column));
}

class $$DraftsTableOrderingComposer
    extends Composer<_$LocalDatabase, $DraftsTable> {
  $$DraftsTableOrderingComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnOrderings<String> get intakeId => $composableBuilder(
      column: $table.intakeId, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<String> get hospitalId => $composableBuilder(
      column: $table.hospitalId, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<String> get hospitalName => $composableBuilder(
      column: $table.hospitalName,
      builder: (column) => ColumnOrderings(column));

  ColumnOrderings<String> get departmentCode => $composableBuilder(
      column: $table.departmentCode,
      builder: (column) => ColumnOrderings(column));

  ColumnOrderings<String> get language => $composableBuilder(
      column: $table.language, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<String> get reporter => $composableBuilder(
      column: $table.reporter, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<String> get answersJson => $composableBuilder(
      column: $table.answersJson, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<String> get contentVersion => $composableBuilder(
      column: $table.contentVersion,
      builder: (column) => ColumnOrderings(column));

  ColumnOrderings<bool> get returnVisit => $composableBuilder(
      column: $table.returnVisit, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<DateTime> get startedAt => $composableBuilder(
      column: $table.startedAt, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<DateTime> get updatedAt => $composableBuilder(
      column: $table.updatedAt, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<String> get queuedPayload => $composableBuilder(
      column: $table.queuedPayload,
      builder: (column) => ColumnOrderings(column));

  ColumnOrderings<String> get idempotencyKey => $composableBuilder(
      column: $table.idempotencyKey,
      builder: (column) => ColumnOrderings(column));
}

class $$DraftsTableAnnotationComposer
    extends Composer<_$LocalDatabase, $DraftsTable> {
  $$DraftsTableAnnotationComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  GeneratedColumn<String> get intakeId =>
      $composableBuilder(column: $table.intakeId, builder: (column) => column);

  GeneratedColumn<String> get hospitalId => $composableBuilder(
      column: $table.hospitalId, builder: (column) => column);

  GeneratedColumn<String> get hospitalName => $composableBuilder(
      column: $table.hospitalName, builder: (column) => column);

  GeneratedColumn<String> get departmentCode => $composableBuilder(
      column: $table.departmentCode, builder: (column) => column);

  GeneratedColumn<String> get language =>
      $composableBuilder(column: $table.language, builder: (column) => column);

  GeneratedColumn<String> get reporter =>
      $composableBuilder(column: $table.reporter, builder: (column) => column);

  GeneratedColumn<String> get answersJson => $composableBuilder(
      column: $table.answersJson, builder: (column) => column);

  GeneratedColumn<String> get contentVersion => $composableBuilder(
      column: $table.contentVersion, builder: (column) => column);

  GeneratedColumn<bool> get returnVisit => $composableBuilder(
      column: $table.returnVisit, builder: (column) => column);

  GeneratedColumn<DateTime> get startedAt =>
      $composableBuilder(column: $table.startedAt, builder: (column) => column);

  GeneratedColumn<DateTime> get updatedAt =>
      $composableBuilder(column: $table.updatedAt, builder: (column) => column);

  GeneratedColumn<String> get queuedPayload => $composableBuilder(
      column: $table.queuedPayload, builder: (column) => column);

  GeneratedColumn<String> get idempotencyKey => $composableBuilder(
      column: $table.idempotencyKey, builder: (column) => column);
}

class $$DraftsTableTableManager extends RootTableManager<
    _$LocalDatabase,
    $DraftsTable,
    Draft,
    $$DraftsTableFilterComposer,
    $$DraftsTableOrderingComposer,
    $$DraftsTableAnnotationComposer,
    $$DraftsTableCreateCompanionBuilder,
    $$DraftsTableUpdateCompanionBuilder,
    (Draft, BaseReferences<_$LocalDatabase, $DraftsTable, Draft>),
    Draft,
    PrefetchHooks Function()> {
  $$DraftsTableTableManager(_$LocalDatabase db, $DraftsTable table)
      : super(TableManagerState(
          db: db,
          table: table,
          createFilteringComposer: () =>
              $$DraftsTableFilterComposer($db: db, $table: table),
          createOrderingComposer: () =>
              $$DraftsTableOrderingComposer($db: db, $table: table),
          createComputedFieldComposer: () =>
              $$DraftsTableAnnotationComposer($db: db, $table: table),
          updateCompanionCallback: ({
            Value<String> intakeId = const Value.absent(),
            Value<String> hospitalId = const Value.absent(),
            Value<String?> hospitalName = const Value.absent(),
            Value<String?> departmentCode = const Value.absent(),
            Value<String> language = const Value.absent(),
            Value<String> reporter = const Value.absent(),
            Value<String> answersJson = const Value.absent(),
            Value<String> contentVersion = const Value.absent(),
            Value<bool> returnVisit = const Value.absent(),
            Value<DateTime> startedAt = const Value.absent(),
            Value<DateTime> updatedAt = const Value.absent(),
            Value<String?> queuedPayload = const Value.absent(),
            Value<String> idempotencyKey = const Value.absent(),
            Value<int> rowid = const Value.absent(),
          }) =>
              DraftsCompanion(
            intakeId: intakeId,
            hospitalId: hospitalId,
            hospitalName: hospitalName,
            departmentCode: departmentCode,
            language: language,
            reporter: reporter,
            answersJson: answersJson,
            contentVersion: contentVersion,
            returnVisit: returnVisit,
            startedAt: startedAt,
            updatedAt: updatedAt,
            queuedPayload: queuedPayload,
            idempotencyKey: idempotencyKey,
            rowid: rowid,
          ),
          createCompanionCallback: ({
            required String intakeId,
            required String hospitalId,
            Value<String?> hospitalName = const Value.absent(),
            Value<String?> departmentCode = const Value.absent(),
            required String language,
            required String reporter,
            required String answersJson,
            required String contentVersion,
            Value<bool> returnVisit = const Value.absent(),
            required DateTime startedAt,
            required DateTime updatedAt,
            Value<String?> queuedPayload = const Value.absent(),
            required String idempotencyKey,
            Value<int> rowid = const Value.absent(),
          }) =>
              DraftsCompanion.insert(
            intakeId: intakeId,
            hospitalId: hospitalId,
            hospitalName: hospitalName,
            departmentCode: departmentCode,
            language: language,
            reporter: reporter,
            answersJson: answersJson,
            contentVersion: contentVersion,
            returnVisit: returnVisit,
            startedAt: startedAt,
            updatedAt: updatedAt,
            queuedPayload: queuedPayload,
            idempotencyKey: idempotencyKey,
            rowid: rowid,
          ),
          withReferenceMapper: (p0) => p0
              .map((e) => (e.readTable(table), BaseReferences(db, table, e)))
              .toList(),
          prefetchHooksCallback: null,
        ));
}

typedef $$DraftsTableProcessedTableManager = ProcessedTableManager<
    _$LocalDatabase,
    $DraftsTable,
    Draft,
    $$DraftsTableFilterComposer,
    $$DraftsTableOrderingComposer,
    $$DraftsTableAnnotationComposer,
    $$DraftsTableCreateCompanionBuilder,
    $$DraftsTableUpdateCompanionBuilder,
    (Draft, BaseReferences<_$LocalDatabase, $DraftsTable, Draft>),
    Draft,
    PrefetchHooks Function()>;
typedef $$PendingDocumentsTableCreateCompanionBuilder
    = PendingDocumentsCompanion Function({
  required String documentId,
  required String intakeId,
  required String filePath,
  Value<String> kind,
  Value<String> status,
  Value<int> attempts,
  required DateTime capturedAt,
  Value<int> rowid,
});
typedef $$PendingDocumentsTableUpdateCompanionBuilder
    = PendingDocumentsCompanion Function({
  Value<String> documentId,
  Value<String> intakeId,
  Value<String> filePath,
  Value<String> kind,
  Value<String> status,
  Value<int> attempts,
  Value<DateTime> capturedAt,
  Value<int> rowid,
});

class $$PendingDocumentsTableFilterComposer
    extends Composer<_$LocalDatabase, $PendingDocumentsTable> {
  $$PendingDocumentsTableFilterComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnFilters<String> get documentId => $composableBuilder(
      column: $table.documentId, builder: (column) => ColumnFilters(column));

  ColumnFilters<String> get intakeId => $composableBuilder(
      column: $table.intakeId, builder: (column) => ColumnFilters(column));

  ColumnFilters<String> get filePath => $composableBuilder(
      column: $table.filePath, builder: (column) => ColumnFilters(column));

  ColumnFilters<String> get kind => $composableBuilder(
      column: $table.kind, builder: (column) => ColumnFilters(column));

  ColumnFilters<String> get status => $composableBuilder(
      column: $table.status, builder: (column) => ColumnFilters(column));

  ColumnFilters<int> get attempts => $composableBuilder(
      column: $table.attempts, builder: (column) => ColumnFilters(column));

  ColumnFilters<DateTime> get capturedAt => $composableBuilder(
      column: $table.capturedAt, builder: (column) => ColumnFilters(column));
}

class $$PendingDocumentsTableOrderingComposer
    extends Composer<_$LocalDatabase, $PendingDocumentsTable> {
  $$PendingDocumentsTableOrderingComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnOrderings<String> get documentId => $composableBuilder(
      column: $table.documentId, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<String> get intakeId => $composableBuilder(
      column: $table.intakeId, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<String> get filePath => $composableBuilder(
      column: $table.filePath, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<String> get kind => $composableBuilder(
      column: $table.kind, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<String> get status => $composableBuilder(
      column: $table.status, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<int> get attempts => $composableBuilder(
      column: $table.attempts, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<DateTime> get capturedAt => $composableBuilder(
      column: $table.capturedAt, builder: (column) => ColumnOrderings(column));
}

class $$PendingDocumentsTableAnnotationComposer
    extends Composer<_$LocalDatabase, $PendingDocumentsTable> {
  $$PendingDocumentsTableAnnotationComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  GeneratedColumn<String> get documentId => $composableBuilder(
      column: $table.documentId, builder: (column) => column);

  GeneratedColumn<String> get intakeId =>
      $composableBuilder(column: $table.intakeId, builder: (column) => column);

  GeneratedColumn<String> get filePath =>
      $composableBuilder(column: $table.filePath, builder: (column) => column);

  GeneratedColumn<String> get kind =>
      $composableBuilder(column: $table.kind, builder: (column) => column);

  GeneratedColumn<String> get status =>
      $composableBuilder(column: $table.status, builder: (column) => column);

  GeneratedColumn<int> get attempts =>
      $composableBuilder(column: $table.attempts, builder: (column) => column);

  GeneratedColumn<DateTime> get capturedAt => $composableBuilder(
      column: $table.capturedAt, builder: (column) => column);
}

class $$PendingDocumentsTableTableManager extends RootTableManager<
    _$LocalDatabase,
    $PendingDocumentsTable,
    PendingDocument,
    $$PendingDocumentsTableFilterComposer,
    $$PendingDocumentsTableOrderingComposer,
    $$PendingDocumentsTableAnnotationComposer,
    $$PendingDocumentsTableCreateCompanionBuilder,
    $$PendingDocumentsTableUpdateCompanionBuilder,
    (
      PendingDocument,
      BaseReferences<_$LocalDatabase, $PendingDocumentsTable, PendingDocument>
    ),
    PendingDocument,
    PrefetchHooks Function()> {
  $$PendingDocumentsTableTableManager(
      _$LocalDatabase db, $PendingDocumentsTable table)
      : super(TableManagerState(
          db: db,
          table: table,
          createFilteringComposer: () =>
              $$PendingDocumentsTableFilterComposer($db: db, $table: table),
          createOrderingComposer: () =>
              $$PendingDocumentsTableOrderingComposer($db: db, $table: table),
          createComputedFieldComposer: () =>
              $$PendingDocumentsTableAnnotationComposer($db: db, $table: table),
          updateCompanionCallback: ({
            Value<String> documentId = const Value.absent(),
            Value<String> intakeId = const Value.absent(),
            Value<String> filePath = const Value.absent(),
            Value<String> kind = const Value.absent(),
            Value<String> status = const Value.absent(),
            Value<int> attempts = const Value.absent(),
            Value<DateTime> capturedAt = const Value.absent(),
            Value<int> rowid = const Value.absent(),
          }) =>
              PendingDocumentsCompanion(
            documentId: documentId,
            intakeId: intakeId,
            filePath: filePath,
            kind: kind,
            status: status,
            attempts: attempts,
            capturedAt: capturedAt,
            rowid: rowid,
          ),
          createCompanionCallback: ({
            required String documentId,
            required String intakeId,
            required String filePath,
            Value<String> kind = const Value.absent(),
            Value<String> status = const Value.absent(),
            Value<int> attempts = const Value.absent(),
            required DateTime capturedAt,
            Value<int> rowid = const Value.absent(),
          }) =>
              PendingDocumentsCompanion.insert(
            documentId: documentId,
            intakeId: intakeId,
            filePath: filePath,
            kind: kind,
            status: status,
            attempts: attempts,
            capturedAt: capturedAt,
            rowid: rowid,
          ),
          withReferenceMapper: (p0) => p0
              .map((e) => (e.readTable(table), BaseReferences(db, table, e)))
              .toList(),
          prefetchHooksCallback: null,
        ));
}

typedef $$PendingDocumentsTableProcessedTableManager = ProcessedTableManager<
    _$LocalDatabase,
    $PendingDocumentsTable,
    PendingDocument,
    $$PendingDocumentsTableFilterComposer,
    $$PendingDocumentsTableOrderingComposer,
    $$PendingDocumentsTableAnnotationComposer,
    $$PendingDocumentsTableCreateCompanionBuilder,
    $$PendingDocumentsTableUpdateCompanionBuilder,
    (
      PendingDocument,
      BaseReferences<_$LocalDatabase, $PendingDocumentsTable, PendingDocument>
    ),
    PendingDocument,
    PrefetchHooks Function()>;
typedef $$ReceiptsTableCreateCompanionBuilder = ReceiptsCompanion Function({
  required String intakeId,
  required String referenceCode,
  required String hospitalName,
  required DateTime submittedAt,
  Value<int> rowid,
});
typedef $$ReceiptsTableUpdateCompanionBuilder = ReceiptsCompanion Function({
  Value<String> intakeId,
  Value<String> referenceCode,
  Value<String> hospitalName,
  Value<DateTime> submittedAt,
  Value<int> rowid,
});

class $$ReceiptsTableFilterComposer
    extends Composer<_$LocalDatabase, $ReceiptsTable> {
  $$ReceiptsTableFilterComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnFilters<String> get intakeId => $composableBuilder(
      column: $table.intakeId, builder: (column) => ColumnFilters(column));

  ColumnFilters<String> get referenceCode => $composableBuilder(
      column: $table.referenceCode, builder: (column) => ColumnFilters(column));

  ColumnFilters<String> get hospitalName => $composableBuilder(
      column: $table.hospitalName, builder: (column) => ColumnFilters(column));

  ColumnFilters<DateTime> get submittedAt => $composableBuilder(
      column: $table.submittedAt, builder: (column) => ColumnFilters(column));
}

class $$ReceiptsTableOrderingComposer
    extends Composer<_$LocalDatabase, $ReceiptsTable> {
  $$ReceiptsTableOrderingComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnOrderings<String> get intakeId => $composableBuilder(
      column: $table.intakeId, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<String> get referenceCode => $composableBuilder(
      column: $table.referenceCode,
      builder: (column) => ColumnOrderings(column));

  ColumnOrderings<String> get hospitalName => $composableBuilder(
      column: $table.hospitalName,
      builder: (column) => ColumnOrderings(column));

  ColumnOrderings<DateTime> get submittedAt => $composableBuilder(
      column: $table.submittedAt, builder: (column) => ColumnOrderings(column));
}

class $$ReceiptsTableAnnotationComposer
    extends Composer<_$LocalDatabase, $ReceiptsTable> {
  $$ReceiptsTableAnnotationComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  GeneratedColumn<String> get intakeId =>
      $composableBuilder(column: $table.intakeId, builder: (column) => column);

  GeneratedColumn<String> get referenceCode => $composableBuilder(
      column: $table.referenceCode, builder: (column) => column);

  GeneratedColumn<String> get hospitalName => $composableBuilder(
      column: $table.hospitalName, builder: (column) => column);

  GeneratedColumn<DateTime> get submittedAt => $composableBuilder(
      column: $table.submittedAt, builder: (column) => column);
}

class $$ReceiptsTableTableManager extends RootTableManager<
    _$LocalDatabase,
    $ReceiptsTable,
    Receipt,
    $$ReceiptsTableFilterComposer,
    $$ReceiptsTableOrderingComposer,
    $$ReceiptsTableAnnotationComposer,
    $$ReceiptsTableCreateCompanionBuilder,
    $$ReceiptsTableUpdateCompanionBuilder,
    (Receipt, BaseReferences<_$LocalDatabase, $ReceiptsTable, Receipt>),
    Receipt,
    PrefetchHooks Function()> {
  $$ReceiptsTableTableManager(_$LocalDatabase db, $ReceiptsTable table)
      : super(TableManagerState(
          db: db,
          table: table,
          createFilteringComposer: () =>
              $$ReceiptsTableFilterComposer($db: db, $table: table),
          createOrderingComposer: () =>
              $$ReceiptsTableOrderingComposer($db: db, $table: table),
          createComputedFieldComposer: () =>
              $$ReceiptsTableAnnotationComposer($db: db, $table: table),
          updateCompanionCallback: ({
            Value<String> intakeId = const Value.absent(),
            Value<String> referenceCode = const Value.absent(),
            Value<String> hospitalName = const Value.absent(),
            Value<DateTime> submittedAt = const Value.absent(),
            Value<int> rowid = const Value.absent(),
          }) =>
              ReceiptsCompanion(
            intakeId: intakeId,
            referenceCode: referenceCode,
            hospitalName: hospitalName,
            submittedAt: submittedAt,
            rowid: rowid,
          ),
          createCompanionCallback: ({
            required String intakeId,
            required String referenceCode,
            required String hospitalName,
            required DateTime submittedAt,
            Value<int> rowid = const Value.absent(),
          }) =>
              ReceiptsCompanion.insert(
            intakeId: intakeId,
            referenceCode: referenceCode,
            hospitalName: hospitalName,
            submittedAt: submittedAt,
            rowid: rowid,
          ),
          withReferenceMapper: (p0) => p0
              .map((e) => (e.readTable(table), BaseReferences(db, table, e)))
              .toList(),
          prefetchHooksCallback: null,
        ));
}

typedef $$ReceiptsTableProcessedTableManager = ProcessedTableManager<
    _$LocalDatabase,
    $ReceiptsTable,
    Receipt,
    $$ReceiptsTableFilterComposer,
    $$ReceiptsTableOrderingComposer,
    $$ReceiptsTableAnnotationComposer,
    $$ReceiptsTableCreateCompanionBuilder,
    $$ReceiptsTableUpdateCompanionBuilder,
    (Receipt, BaseReferences<_$LocalDatabase, $ReceiptsTable, Receipt>),
    Receipt,
    PrefetchHooks Function()>;

class $LocalDatabaseManager {
  final _$LocalDatabase _db;
  $LocalDatabaseManager(this._db);
  $$DraftsTableTableManager get drafts =>
      $$DraftsTableTableManager(_db, _db.drafts);
  $$PendingDocumentsTableTableManager get pendingDocuments =>
      $$PendingDocumentsTableTableManager(_db, _db.pendingDocuments);
  $$ReceiptsTableTableManager get receipts =>
      $$ReceiptsTableTableManager(_db, _db.receipts);
}
