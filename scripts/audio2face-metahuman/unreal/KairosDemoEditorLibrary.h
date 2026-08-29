/*
 * SPDX-FileCopyrightText: Copyright (c) 2026
 * SPDX-License-Identifier: MIT
 */

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "KairosDemoEditorLibrary.generated.h"

UCLASS()
class KAIROSSAMPLE_API UKairosDemoEditorLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/** Replace the crash-prone full Jesse actor with a diagnostic face-only ACE actor. */
	UFUNCTION(BlueprintCallable, Category = "ACE Demo")
	static bool ConfigureDiagnosticJesseFace();

	/** Log the original BP_Jesse SCS component templates without spawning the actor. */
	UFUNCTION(BlueprintCallable, Category = "ACE Demo|Diagnostics")
	static bool InventoryOriginalJesseBlueprint();

	/** Spawn original BP_Jesse and change only visual-component visibility for a reversible A/B map. */
	UFUNCTION(BlueprintCallable, Category = "ACE Demo|Diagnostics")
	static bool ConfigureOriginalJesseVariant(const FString& VariantName, const TArray<FName>& VisibleComponents);

	/** Configure one clothing component on a duplicated map; source BP and assets remain unchanged. */
	UFUNCTION(BlueprintCallable, Category = "ACE Demo|Diagnostics")
	static bool ConfigureOriginalJesseClothingProbe(
		const FString& VariantName,
		FName ComponentName,
		const FString& MaterialOverridePath,
		const FString& MeshOverridePath,
		int32 ForcedLOD);

	/** Turn the stable original BP_Jesse face+groom visibility map into the final A2F face demo. */
	UFUNCTION(BlueprintCallable, Category = "ACE Demo")
	static bool ConfigureOriginalJesseFaceDemo();

	/** Configure the official BP_Taro preset as the clothed, face-focused A2F demo actor. */
	UFUNCTION(BlueprintCallable, Category = "ACE Demo")
	static bool ConfigureOriginalTaroFaceDemo();

	/** Prepare only a run-owned MetaHuman actor instance for ACE; source assets are unchanged. */
	UFUNCTION(BlueprintCallable, Category = "ACE Demo")
	static bool ConfigureMetaHumanActorForACE(AActor* MetaHumanActor);

	/** Configure the official Apply ACE Face Animations node on this PIE actor only. */
	UFUNCTION(BlueprintCallable, Category = "ACE Demo|Animation")
	static int32 ConfigureACEBlendshapeOverrides(
		AActor* MetaHumanActor,
		const TMap<FName, float>& Multipliers,
		const TMap<FName, float>& Offsets);

	/** Replace float-curve keys in one bracket so compression happens once. */
	UFUNCTION(BlueprintCallable, Category = "ACE Demo|Animation")
	static bool ApplyFloatCurvesBulk(
		class UAnimSequence* Animation,
		const TArray<FName>& CurveNames,
		const TArray<float>& Times,
		const TArray<float>& CurveMajorValues);

	/** Bake local head/neck rotation deltas into a duplicated run-owned Body animation. */
	UFUNCTION(BlueprintCallable, Category = "ACE Demo|Animation")
	static bool ApplyHeadRotationsToBodyAnimation(
		class UAnimSequence* Animation,
		int32 StartFrame,
		int32 ExpectedFrameRate,
		const TArray<FName>& BoneNames,
		const TArray<float>& BoneWeights,
		const TArray<FRotator>& FrameRotations);

	/** Read maximum authored bone-rotation deltas from a run-owned Body animation. */
	UFUNCTION(BlueprintPure, Category = "ACE Demo|Animation")
	static TArray<float> GetBodyAnimationBoneRotationDeltas(
		class UAnimSequence* Animation,
		int32 StartFrame,
		int32 FrameCount,
		const TArray<FName>& BoneNames);
};
