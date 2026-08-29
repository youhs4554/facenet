/*
 * SPDX-FileCopyrightText: Copyright (c) 2026
 * SPDX-License-Identifier: MIT
 */

#include "KairosDemoEditorLibrary.h"

#include "Animation/AnimInstance.h"
#include "Animation/AnimClassInterface.h"
#include "Animation/AnimData/IAnimationDataController.h"
#include "Animation/AnimData/IAnimationDataModel.h"
#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "ACEAudioCurveSourceComponent.h"
#include "AnimNode_ApplyACEAnimation.h"
#include "Components/MeshComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Editor.h"
#include "Engine/Blueprint.h"
#include "Engine/BlueprintGeneratedClass.h"
#include "Engine/SCS_Node.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/SimpleConstructionScript.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerStart.h"
#include "SimplifiedACEFaceActor.h"
#include "UObject/UnrealType.h"

#define LOCTEXT_NAMESPACE "KairosDemoEditorLibrary"

bool UKairosDemoEditorLibrary::ConfigureDiagnosticJesseFace()
{
#if WITH_EDITOR
	if (!GEditor)
	{
		UE_LOG(LogTemp, Error, TEXT("[A2F-DEMO] GEditor is unavailable"));
		return false;
	}

	UWorld* World = GEditor->GetEditorWorldContext().World();
	if (!World)
	{
		UE_LOG(LogTemp, Error, TEXT("[A2F-DEMO] Editor world is unavailable"));
		return false;
	}

	FTransform SpawnTransform(FRotator::ZeroRotator, FVector(0.0, 0.0, 150.0));
	TArray<AActor*> ActorsToRemove;

	for (TActorIterator<AActor> It(World); It; ++It)
	{
		AActor* Actor = *It;
		const FString ClassName = Actor->GetClass()->GetName();

		if (ClassName == TEXT("BP_Jesse_C"))
		{
			SpawnTransform = Actor->GetActorTransform();

			TInlineComponentArray<USkeletalMeshComponent*> SkeletalComponents(Actor);
			for (USkeletalMeshComponent* Component : SkeletalComponents)
			{
				if (Component && Component->GetName() == TEXT("Face"))
				{
					SpawnTransform = Component->GetComponentTransform();
					break;
				}
			}

			ActorsToRemove.Add(Actor);
		}
		else if (ClassName == TEXT("SimplifiedACEFaceActor"))
		{
			ActorsToRemove.Add(Actor);
		}
	}

	for (AActor* Actor : ActorsToRemove)
	{
		World->EditorDestroyActor(Actor, true);
	}

	USkeletalMesh* FaceMesh = LoadObject<USkeletalMesh>(
		nullptr,
		TEXT("/Game/MetaHumans/Jesse/Face/Jesse_FaceMesh.Jesse_FaceMesh"));
	UClass* FaceAnimClass = LoadObject<UClass>(
		nullptr,
		TEXT("/Game/MetaHumans/Common/Face/Face_AnimBP.Face_AnimBP_C"));

	if (!FaceMesh || !FaceAnimClass)
	{
		UE_LOG(LogTemp, Error, TEXT("[A2F-DEMO] Jesse face mesh or ACE Face_AnimBP is missing"));
		return false;
	}

	FActorSpawnParameters SpawnParameters;
	SpawnParameters.OverrideLevel = World->GetCurrentLevel();
	SpawnParameters.ObjectFlags |= RF_Transactional;

	ASimplifiedACEFaceActor* FaceActor = World->SpawnActor<ASimplifiedACEFaceActor>(
		ASimplifiedACEFaceActor::StaticClass(),
		SpawnTransform,
		SpawnParameters);

	if (!FaceActor)
	{
		UE_LOG(LogTemp, Error, TEXT("[A2F-DEMO] Failed to spawn simplified Jesse face"));
		return false;
	}

	FaceActor->SetActorLabel(TEXT("Jesse_ACE_DiagnosticFaceOnly"));
	FaceActor->Face->SetSkeletalMeshAsset(FaceMesh);
	FaceActor->Face->SetAnimInstanceClass(FaceAnimClass);
	FaceActor->MarkPackageDirty();
	World->MarkPackageDirty();

	UE_LOG(
		LogTemp,
		Display,
		TEXT("[A2F-DEMO] configured diagnostic Jesse face-only actor with %d face material slots"),
		FaceMesh->GetMaterials().Num());
	return true;
#else
	return false;
#endif
}

bool UKairosDemoEditorLibrary::InventoryOriginalJesseBlueprint()
{
#if WITH_EDITOR
	UBlueprint* Blueprint = LoadObject<UBlueprint>(
		nullptr,
		TEXT("/Game/MetaHumans/Jesse/BP_Jesse.BP_Jesse"));
	if (!Blueprint || !Blueprint->SimpleConstructionScript)
	{
		UE_LOG(LogTemp, Error, TEXT("[JESSE-INVENTORY] BP_Jesse or its SCS is unavailable"));
		return false;
	}

	UBlueprintGeneratedClass* GeneratedClass = Cast<UBlueprintGeneratedClass>(Blueprint->GeneratedClass);
	const TArray<USCS_Node*> Nodes = Blueprint->SimpleConstructionScript->GetAllNodes();
	UE_LOG(LogTemp, Display, TEXT("[JESSE-INVENTORY] blueprint=%s nodes=%d"), *Blueprint->GetPathName(), Nodes.Num());

	const FName AssetProperties[] = {
		TEXT("SkeletalMeshAsset"),
		TEXT("SkeletalMesh"),
		TEXT("GroomAsset"),
		TEXT("BindingAsset"),
		TEXT("StaticMesh"),
	};
	const FName LODProperties[] = {
		TEXT("ForcedLOD"),
		TEXT("ForcedLodModel"),
		TEXT("MinLOD"),
		TEXT("OverrideMinLOD"),
	};

	for (USCS_Node* Node : Nodes)
	{
		if (!Node)
		{
			continue;
		}

		UActorComponent* Component = Node->GetActualComponentTemplate(GeneratedClass);
		if (!Component)
		{
			Component = Node->ComponentTemplate;
		}
		if (!Component)
		{
			continue;
		}

		TArray<FString> PropertyValues;
		for (const FName PropertyName : AssetProperties)
		{
			if (FProperty* Property = Component->GetClass()->FindPropertyByName(PropertyName))
			{
				FString Value;
				Property->ExportText_InContainer(0, Value, Component, Component, Component, PPF_None);
				PropertyValues.Add(PropertyName.ToString() + TEXT("=") + Value);
			}
		}
		for (const FName PropertyName : LODProperties)
		{
			if (FProperty* Property = Component->GetClass()->FindPropertyByName(PropertyName))
			{
				FString Value;
				Property->ExportText_InContainer(0, Value, Component, Component, Component, PPF_None);
				PropertyValues.Add(PropertyName.ToString() + TEXT("=") + Value);
			}
		}

		TArray<FString> Materials;
		if (UMeshComponent* MeshComponent = Cast<UMeshComponent>(Component))
		{
			for (int32 MaterialIndex = 0; MaterialIndex < MeshComponent->GetNumMaterials(); ++MaterialIndex)
			{
				UMaterialInterface* Material = MeshComponent->GetMaterial(MaterialIndex);
				Materials.Add(Material ? Material->GetPathName() : TEXT("None"));
			}
		}
		if (USkeletalMeshComponent* SkeletalComponent = Cast<USkeletalMeshComponent>(Component))
		{
			if (USkeletalMesh* SkeletalMesh = SkeletalComponent->GetSkeletalMeshAsset())
			{
				PropertyValues.Add(FString::Printf(TEXT("MeshLODCount=%d"), SkeletalMesh->GetLODNum()));
				for (const FSkeletalMaterial& SkeletalMaterial : SkeletalMesh->GetMaterials())
				{
					Materials.Add(SkeletalMaterial.MaterialInterface
						? SkeletalMaterial.MaterialInterface->GetPathName()
						: TEXT("None"));
				}
			}
		}

		UE_LOG(
			LogTemp,
			Display,
			TEXT("[JESSE-INVENTORY] component=%s class=%s parent=%s properties=[%s] materials=[%s]"),
			*Node->GetVariableName().ToString(),
			*Component->GetClass()->GetName(),
			*Node->ParentComponentOrVariableName.ToString(),
			*FString::Join(PropertyValues, TEXT(";")),
			*FString::Join(Materials, TEXT(";")));
	}

	UE_LOG(LogTemp, Display, TEXT("[JESSE-INVENTORY] done"));
	return true;
#else
	return false;
#endif
}

bool UKairosDemoEditorLibrary::ConfigureOriginalJesseVariant(
	const FString& VariantName,
	const TArray<FName>& VisibleComponents)
{
#if WITH_EDITOR
	if (!GEditor)
	{
		UE_LOG(LogTemp, Error, TEXT("[JESSE-AB] GEditor is unavailable"));
		return false;
	}

	UWorld* World = GEditor->GetEditorWorldContext().World();
	if (!World)
	{
		UE_LOG(LogTemp, Error, TEXT("[JESSE-AB] Editor world is unavailable"));
		return false;
	}

	TArray<AActor*> ActorsToRemove;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		const FString ClassName = It->GetClass()->GetName();
		if (ClassName == TEXT("BP_Jesse_C") || ClassName == TEXT("SimplifiedACEFaceActor"))
		{
			ActorsToRemove.Add(*It);
		}
	}
	for (AActor* Actor : ActorsToRemove)
	{
		World->EditorDestroyActor(Actor, true);
	}

	UClass* JesseClass = LoadObject<UClass>(
		nullptr,
		TEXT("/Game/MetaHumans/Jesse/BP_Jesse.BP_Jesse_C"));
	if (!JesseClass)
	{
		UE_LOG(LogTemp, Error, TEXT("[JESSE-AB] BP_Jesse class is unavailable"));
		return false;
	}

	FActorSpawnParameters SpawnParameters;
	SpawnParameters.OverrideLevel = World->GetCurrentLevel();
	SpawnParameters.ObjectFlags |= RF_Transactional;
	AActor* JesseActor = World->SpawnActor<AActor>(
		JesseClass,
		FTransform(FRotator::ZeroRotator, FVector(-100.0, 0.0, 0.0)),
		SpawnParameters);
	if (!JesseActor)
	{
		UE_LOG(LogTemp, Error, TEXT("[JESSE-AB] Failed to spawn BP_Jesse"));
		return false;
	}

	JesseActor->SetActorLabel(TEXT("BP_Jesse_AB_") + VariantName);
	TSet<FName> VisibleSet;
	for (const FName ComponentName : VisibleComponents)
	{
		VisibleSet.Add(ComponentName);
	}
	const TSet<FName> VisualComponentNames = {
		TEXT("Body"), TEXT("Face"), TEXT("Hair"), TEXT("Eyebrows"),
		TEXT("Fuzz"), TEXT("Torso"), TEXT("Legs"), TEXT("Feet"),
		TEXT("Eyelashes"), TEXT("Mustache"), TEXT("Beard"),
	};

	TInlineComponentArray<UPrimitiveComponent*> PrimitiveComponents(JesseActor);
	for (UPrimitiveComponent* Component : PrimitiveComponents)
	{
		if (!Component || !VisualComponentNames.Contains(Component->GetFName()))
		{
			continue;
		}
		const bool bVisible = VisibleSet.Contains(Component->GetFName());
		Component->SetVisibility(bVisible, true);
		Component->SetHiddenInGame(!bVisible, true);
		Component->MarkRenderStateDirty();
		UE_LOG(
			LogTemp,
			Display,
			TEXT("[JESSE-AB] variant=%s component=%s visible=%s"),
			*VariantName,
			*Component->GetName(),
			bVisible ? TEXT("true") : TEXT("false"));
	}

	JesseActor->MarkPackageDirty();
	World->MarkPackageDirty();
	UE_LOG(LogTemp, Display, TEXT("[JESSE-AB] configured variant=%s"), *VariantName);
	return true;
#else
	return false;
#endif
}

bool UKairosDemoEditorLibrary::ConfigureOriginalJesseClothingProbe(
	const FString& VariantName,
	FName ComponentName,
	const FString& MaterialOverridePath,
	const FString& MeshOverridePath,
	int32 ForcedLOD)
{
#if WITH_EDITOR
	if (!ConfigureOriginalJesseVariant(VariantName, {TEXT("Face"), ComponentName}))
	{
		return false;
	}

	UWorld* World = GEditor ? GEditor->GetEditorWorldContext().World() : nullptr;
	if (!World)
	{
		return false;
	}

	AActor* JesseActor = nullptr;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (It->GetClass()->GetName() == TEXT("BP_Jesse_C"))
		{
			JesseActor = *It;
			break;
		}
	}
	if (!JesseActor)
	{
		UE_LOG(LogTemp, Error, TEXT("[JESSE-PROBE] Spawned BP_Jesse was not found"));
		return false;
	}

	USkeletalMeshComponent* TargetComponent = nullptr;
	TInlineComponentArray<USkeletalMeshComponent*> SkeletalComponents(JesseActor);
	for (USkeletalMeshComponent* Component : SkeletalComponents)
	{
		if (Component && Component->GetFName() == ComponentName)
		{
			TargetComponent = Component;
			break;
		}
	}
	if (!TargetComponent)
	{
		UE_LOG(LogTemp, Error, TEXT("[JESSE-PROBE] Component %s was not found"), *ComponentName.ToString());
		return false;
	}

	if (!MeshOverridePath.IsEmpty())
	{
		USkeletalMesh* MeshOverride = LoadObject<USkeletalMesh>(nullptr, *MeshOverridePath);
		if (!MeshOverride)
		{
			UE_LOG(LogTemp, Error, TEXT("[JESSE-PROBE] Mesh override was not found: %s"), *MeshOverridePath);
			return false;
		}
		TargetComponent->SetSkeletalMeshAsset(MeshOverride);
	}

	if (!MaterialOverridePath.IsEmpty())
	{
		UMaterialInterface* MaterialOverride = LoadObject<UMaterialInterface>(nullptr, *MaterialOverridePath);
		if (!MaterialOverride)
		{
			UE_LOG(LogTemp, Error, TEXT("[JESSE-PROBE] Material override was not found: %s"), *MaterialOverridePath);
			return false;
		}
		const int32 MaterialCount = TargetComponent->GetNumMaterials();
		for (int32 MaterialIndex = 0; MaterialIndex < MaterialCount; ++MaterialIndex)
		{
			TargetComponent->SetMaterial(MaterialIndex, MaterialOverride);
		}
	}

	if (ForcedLOD >= 0)
	{
		TargetComponent->SetForcedLOD(ForcedLOD);
	}

	JesseActor->SetActorLabel(TEXT("BP_Jesse_Probe_") + VariantName);
	JesseActor->MarkPackageDirty();
	World->MarkPackageDirty();
	UE_LOG(
		LogTemp,
		Display,
		TEXT("[JESSE-PROBE] variant=%s component=%s mesh=%s material=%s forced_lod=%d slots=%d"),
		*VariantName,
		*ComponentName.ToString(),
		TargetComponent->GetSkeletalMeshAsset() ? *TargetComponent->GetSkeletalMeshAsset()->GetPathName() : TEXT("None"),
		MaterialOverridePath.IsEmpty() ? TEXT("original") : *MaterialOverridePath,
		ForcedLOD,
		TargetComponent->GetNumMaterials());
	return true;
#else
	return false;
#endif
}

bool UKairosDemoEditorLibrary::ConfigureOriginalJesseFaceDemo()
{
#if WITH_EDITOR
	UWorld* World = GEditor ? GEditor->GetEditorWorldContext().World() : nullptr;
	if (!World)
	{
		UE_LOG(LogTemp, Error, TEXT("[JESSE-FACE-DEMO] Editor world is unavailable"));
		return false;
	}

	AActor* JesseActor = nullptr;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (It->GetClass()->GetName() == TEXT("BP_Jesse_C"))
		{
			JesseActor = *It;
			break;
		}
	}
	if (!JesseActor)
	{
		UE_LOG(LogTemp, Error, TEXT("[JESSE-FACE-DEMO] Original BP_Jesse actor was not found"));
		return false;
	}

	JesseActor->Modify();
	const TSet<FName> FaceVisuals = {
		TEXT("Face"), TEXT("Hair"), TEXT("Eyebrows"), TEXT("Fuzz"),
		TEXT("Eyelashes"), TEXT("Mustache"), TEXT("Beard"), TEXT("Body"), TEXT("Torso"),
	};
	const TSet<FName> BodyVisuals = {
		TEXT("Legs"), TEXT("Feet"),
	};

	USkeletalMeshComponent* FaceComponent = nullptr;
	USkeletalMeshComponent* TorsoComponent = nullptr;
	TInlineComponentArray<UPrimitiveComponent*> PrimitiveComponents(JesseActor);
	for (UPrimitiveComponent* Component : PrimitiveComponents)
	{
		if (!Component)
		{
			continue;
		}
		if (FaceVisuals.Contains(Component->GetFName()))
		{
			Component->SetVisibility(true, true);
			Component->SetHiddenInGame(false, true);
		}
		else if (BodyVisuals.Contains(Component->GetFName()))
		{
			Component->SetVisibility(false, true);
			Component->SetHiddenInGame(true, true);
		}
		if (Component->GetFName() == TEXT("Face"))
		{
			FaceComponent = Cast<USkeletalMeshComponent>(Component);
		}
		else if (Component->GetFName() == TEXT("Torso"))
		{
			TorsoComponent = Cast<USkeletalMeshComponent>(Component);
		}
	}

	UClass* FaceAnimClass = LoadObject<UClass>(
		nullptr,
		TEXT("/Game/MetaHumans/Common/Face/Face_AnimBP.Face_AnimBP_C"));
	if (!FaceComponent || !FaceAnimClass)
	{
		UE_LOG(LogTemp, Error, TEXT("[JESSE-FACE-DEMO] Face component or ACE Face_AnimBP is unavailable"));
		return false;
	}
	FaceComponent->SetAnimInstanceClass(FaceAnimClass);

	UMaterialInterface* SafeShirtMaterial = LoadObject<UMaterialInterface>(
		nullptr,
		TEXT("/Game/Audio2FaceDemo/Materials/M_JesseShirt_VulkanSafe.M_JesseShirt_VulkanSafe"));
	if (!TorsoComponent || !SafeShirtMaterial)
	{
		UE_LOG(LogTemp, Error, TEXT("[JESSE-FACE-DEMO] Torso component or safe shirt material is unavailable"));
		return false;
	}
	for (int32 MaterialIndex = 0; MaterialIndex < TorsoComponent->GetNumMaterials(); ++MaterialIndex)
	{
		TorsoComponent->SetMaterial(MaterialIndex, SafeShirtMaterial);
	}

	UACEAudioCurveSourceComponent* ACEComponent = JesseActor->FindComponentByClass<UACEAudioCurveSourceComponent>();
	if (!ACEComponent)
	{
		ACEComponent = NewObject<UACEAudioCurveSourceComponent>(
			JesseActor,
			TEXT("ACEAudioCurveSource"),
			RF_Transactional);
		ACEComponent->CreationMethod = EComponentCreationMethod::Instance;
		JesseActor->AddInstanceComponent(ACEComponent);
		ACEComponent->SetupAttachment(JesseActor->GetRootComponent());
		ACEComponent->RegisterComponent();
	}

	for (TActorIterator<APlayerStart> It(World); It; ++It)
	{
		It->Modify();
		It->SetActorLocation(FVector(-100.0, 120.0, 100.0));
		It->SetActorRotation(FRotator(0.0, -90.0, 0.0));
		It->MarkPackageDirty();
		break;
	}

	JesseActor->SetActorLabel(TEXT("Jesse_A2F_FaceDemo"));
	JesseActor->MarkPackageDirty();
	World->MarkPackageDirty();
	UE_LOG(
		LogTemp,
		Display,
		TEXT("[JESSE-FACE-DEMO] configured actor=%s face=%s torso=%s shirt=%s anim=%s ace=%s"),
		*JesseActor->GetClass()->GetPathName(),
		FaceComponent->GetSkeletalMeshAsset() ? *FaceComponent->GetSkeletalMeshAsset()->GetPathName() : TEXT("None"),
		TorsoComponent->GetSkeletalMeshAsset() ? *TorsoComponent->GetSkeletalMeshAsset()->GetPathName() : TEXT("None"),
		*SafeShirtMaterial->GetPathName(),
		*FaceAnimClass->GetPathName(),
		*ACEComponent->GetName());
	return true;
#else
	return false;
#endif
}

bool UKairosDemoEditorLibrary::ConfigureOriginalTaroFaceDemo()
{
#if WITH_EDITOR
	UWorld* World = GEditor ? GEditor->GetEditorWorldContext().World() : nullptr;
	if (!World)
	{
		UE_LOG(LogTemp, Error, TEXT("[TARO-A2F-DEMO] Editor world is unavailable"));
		return false;
	}

	FTransform SpawnTransform(FRotator::ZeroRotator, FVector::ZeroVector);
	TArray<AActor*> MetaHumansToRemove;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		const FString ClassName = It->GetClass()->GetName();
		if (ClassName == TEXT("BP_Jesse_C") || ClassName == TEXT("BP_Taro_C"))
		{
			SpawnTransform = It->GetActorTransform();
			MetaHumansToRemove.Add(*It);
		}
	}
	for (AActor* Actor : MetaHumansToRemove)
	{
		World->EditorDestroyActor(Actor, true);
	}

	UClass* TaroClass = LoadObject<UClass>(
		nullptr,
		TEXT("/Game/MetaHumans/Taro/BP_Taro.BP_Taro_C"));
	if (!TaroClass)
	{
		UE_LOG(LogTemp, Error, TEXT("[TARO-A2F-DEMO] Official BP_Taro class is unavailable"));
		return false;
	}

	FActorSpawnParameters SpawnParameters;
	SpawnParameters.OverrideLevel = World->GetCurrentLevel();
	SpawnParameters.ObjectFlags |= RF_Transactional;
	AActor* TaroActor = World->SpawnActor<AActor>(TaroClass, SpawnTransform, SpawnParameters);
	if (!TaroActor)
	{
		UE_LOG(LogTemp, Error, TEXT("[TARO-A2F-DEMO] Could not spawn official BP_Taro"));
		return false;
	}

	TaroActor->Modify();
	const TSet<FName> VisibleVisuals = {
		TEXT("Face"), TEXT("Hair"), TEXT("Eyebrows"), TEXT("Fuzz"),
		TEXT("Eyelashes"), TEXT("Mustache"), TEXT("Beard"), TEXT("Body"), TEXT("Torso"),
	};
	const TSet<FName> HiddenVisuals = {
		TEXT("Legs"), TEXT("Feet"),
	};

	USkeletalMeshComponent* FaceComponent = nullptr;
	USkeletalMeshComponent* TorsoComponent = nullptr;
	TInlineComponentArray<UPrimitiveComponent*> PrimitiveComponents(TaroActor);
	for (UPrimitiveComponent* Component : PrimitiveComponents)
	{
		if (!Component)
		{
			continue;
		}
		if (VisibleVisuals.Contains(Component->GetFName()))
		{
			Component->SetVisibility(true, true);
			Component->SetHiddenInGame(false, true);
		}
		else if (HiddenVisuals.Contains(Component->GetFName()))
		{
			Component->SetVisibility(false, true);
			Component->SetHiddenInGame(true, true);
		}
		if (Component->GetFName() == TEXT("Face"))
		{
			FaceComponent = Cast<USkeletalMeshComponent>(Component);
		}
		else if (Component->GetFName() == TEXT("Torso"))
		{
			TorsoComponent = Cast<USkeletalMeshComponent>(Component);
		}
	}

	UClass* FaceAnimClass = LoadObject<UClass>(
		nullptr,
		TEXT("/Game/MetaHumans/Common/Face/Face_AnimBP.Face_AnimBP_C"));
	if (!FaceComponent || !FaceAnimClass)
	{
		UE_LOG(LogTemp, Error, TEXT("[TARO-A2F-DEMO] Face component or ACE Face_AnimBP is unavailable"));
		return false;
	}
	FaceComponent->SetAnimInstanceClass(FaceAnimClass);

	UMaterialInterface* SafeTopMaterial = LoadObject<UMaterialInterface>(
		nullptr,
		TEXT("/Game/Audio2FaceDemo/Materials/M_TaroTop_VulkanSafe.M_TaroTop_VulkanSafe"));
	if (!TorsoComponent || !SafeTopMaterial)
	{
		UE_LOG(LogTemp, Error, TEXT("[TARO-A2F-DEMO] Torso component or safe top material is unavailable"));
		return false;
	}
	for (int32 MaterialIndex = 0; MaterialIndex < TorsoComponent->GetNumMaterials(); ++MaterialIndex)
	{
		TorsoComponent->SetMaterial(MaterialIndex, SafeTopMaterial);
	}

	UACEAudioCurveSourceComponent* ACEComponent = TaroActor->FindComponentByClass<UACEAudioCurveSourceComponent>();
	if (!ACEComponent)
	{
		ACEComponent = NewObject<UACEAudioCurveSourceComponent>(
			TaroActor,
			TEXT("ACEAudioCurveSource"),
			RF_Transactional);
		ACEComponent->CreationMethod = EComponentCreationMethod::Instance;
		TaroActor->AddInstanceComponent(ACEComponent);
		ACEComponent->SetupAttachment(TaroActor->GetRootComponent());
		ACEComponent->RegisterComponent();
	}

	for (TActorIterator<APlayerStart> It(World); It; ++It)
	{
		It->Modify();
		It->SetActorLocation(FVector(-100.0, 120.0, 100.0));
		It->SetActorRotation(FRotator(0.0, -90.0, 0.0));
		It->MarkPackageDirty();
		break;
	}

	TaroActor->SetActorLabel(TEXT("Taro_A2F_FaceBodyDemo"));
	TaroActor->MarkPackageDirty();
	World->MarkPackageDirty();
	UE_LOG(
		LogTemp,
		Display,
		TEXT("[TARO-A2F-DEMO] configured actor=%s face=%s torso=%s top=%s anim=%s ace=%s body_visible=true legs_visible=false"),
		*TaroActor->GetClass()->GetPathName(),
		FaceComponent->GetSkeletalMeshAsset() ? *FaceComponent->GetSkeletalMeshAsset()->GetPathName() : TEXT("None"),
		TorsoComponent->GetSkeletalMeshAsset() ? *TorsoComponent->GetSkeletalMeshAsset()->GetPathName() : TEXT("None"),
		*SafeTopMaterial->GetPathName(),
		*FaceAnimClass->GetPathName(),
		*ACEComponent->GetName());
	return true;
#else
	return false;
#endif
}

bool UKairosDemoEditorLibrary::ConfigureMetaHumanActorForACE(AActor* MetaHumanActor)
{
#if WITH_EDITOR
	if (!MetaHumanActor)
	{
		UE_LOG(LogTemp, Error, TEXT("[METAHUMAN-A2F] actor is null"));
		return false;
	}

	USkeletalMeshComponent* FaceComponent = nullptr;
	TInlineComponentArray<USkeletalMeshComponent*> SkeletalComponents(MetaHumanActor);
	for (USkeletalMeshComponent* Component : SkeletalComponents)
	{
		if (Component && Component->GetFName() == TEXT("Face"))
		{
			FaceComponent = Component;
			break;
		}
	}

	UClass* FaceAnimClass = LoadObject<UClass>(
		nullptr,
		TEXT("/Game/MetaHumans/Common/Face/Face_AnimBP.Face_AnimBP_C"));
	if (!FaceComponent || !FaceComponent->GetSkeletalMeshAsset() || !FaceAnimClass)
	{
		UE_LOG(LogTemp, Error, TEXT("[METAHUMAN-A2F] Face mesh or ACE Face_AnimBP is unavailable"));
		return false;
	}
	IAnimClassInterface* AnimClassInterface = IAnimClassInterface::GetFromClass(FaceAnimClass);
	USkeleton* FaceSkeleton = FaceComponent->GetSkeletalMeshAsset()->GetSkeleton();
	USkeleton* TargetSkeleton = AnimClassInterface ? AnimClassInterface->GetTargetSkeleton() : nullptr;
	if (!FaceSkeleton || !TargetSkeleton || !FaceSkeleton->IsCompatibleForEditor(TargetSkeleton))
	{
		UE_LOG(LogTemp, Error, TEXT("[METAHUMAN-A2F] Face mesh skeleton is incompatible with ACE Face_AnimBP"));
		return false;
	}
	FaceComponent->SetAnimInstanceClass(FaceAnimClass);

	UACEAudioCurveSourceComponent* ACEComponent = MetaHumanActor->FindComponentByClass<UACEAudioCurveSourceComponent>();
	if (!ACEComponent)
	{
		ACEComponent = NewObject<UACEAudioCurveSourceComponent>(
			MetaHumanActor,
			TEXT("ACEAudioCurveSource"),
			RF_Transactional);
		ACEComponent->CreationMethod = EComponentCreationMethod::Instance;
		MetaHumanActor->AddInstanceComponent(ACEComponent);
		ACEComponent->SetupAttachment(MetaHumanActor->GetRootComponent());
		ACEComponent->RegisterComponent();
	}

	MetaHumanActor->Modify();
	MetaHumanActor->MarkPackageDirty();
	if (UWorld* World = MetaHumanActor->GetWorld())
	{
		World->MarkPackageDirty();
	}
	UE_LOG(
		LogTemp,
		Display,
		TEXT("[METAHUMAN-A2F] prepared actor=%s face=%s anim=%s ace=%s"),
		*MetaHumanActor->GetClass()->GetPathName(),
		*FaceComponent->GetSkeletalMeshAsset()->GetPathName(),
		*FaceAnimClass->GetPathName(),
		*ACEComponent->GetName());
	return true;
#else
	return false;
#endif
}

int32 UKairosDemoEditorLibrary::ConfigureACEBlendshapeOverrides(
	AActor* MetaHumanActor,
	const TMap<FName, float>& Multipliers,
	const TMap<FName, float>& Offsets)
{
	if (!MetaHumanActor)
	{
		UE_LOG(LogTemp, Error, TEXT("[METAHUMAN-A2F] override actor is null"));
		return 0;
	}

	USkeletalMeshComponent* FaceComponent = nullptr;
	TInlineComponentArray<USkeletalMeshComponent*> SkeletalComponents(MetaHumanActor);
	for (USkeletalMeshComponent* Component : SkeletalComponents)
	{
		if (Component && Component->GetFName() == TEXT("Face"))
		{
			FaceComponent = Component;
			break;
		}
	}
	UAnimInstance* AnimInstance = FaceComponent ? FaceComponent->GetAnimInstance() : nullptr;
	if (!AnimInstance)
	{
		UE_LOG(LogTemp, Error, TEXT("[METAHUMAN-A2F] Face AnimInstance is unavailable"));
		return 0;
	}

	int32 ModifiedNodes = 0;
	for (TFieldIterator<FStructProperty> PropertyIt(
		AnimInstance->GetClass(), EFieldIteratorFlags::IncludeSuper);
		PropertyIt;
		++PropertyIt)
	{
		FStructProperty* Property = *PropertyIt;
		if (!Property || Property->Struct != FAnimNode_ApplyACEAnimation::StaticStruct())
		{
			continue;
		}
		FAnimNode_ApplyACEAnimation* Node =
			Property->ContainerPtrToValuePtr<FAnimNode_ApplyACEAnimation>(AnimInstance);
		if (!Node)
		{
			continue;
		}
		Node->BlendshapeMultipliers = Multipliers;
		Node->BlendshapeOffsets = Offsets;
		++ModifiedNodes;
	}
	if (ModifiedNodes > 0)
	{
		UE_LOG(
			LogTemp,
			Display,
			TEXT("[METAHUMAN-A2F] ACE node overrides nodes=%d multipliers=%d offsets=%d actor=%s"),
			ModifiedNodes,
			Multipliers.Num(),
			Offsets.Num(),
			*MetaHumanActor->GetName());
	}
	else
	{
		UE_LOG(
			LogTemp,
			Error,
			TEXT("[METAHUMAN-A2F] no Apply ACE Face Animations node found on actor=%s"),
			*MetaHumanActor->GetName());
	}
	return ModifiedNodes;
}

bool UKairosDemoEditorLibrary::ApplyFloatCurvesBulk(
	UAnimSequence* Animation,
	const TArray<FName>& CurveNames,
	const TArray<float>& Times,
	const TArray<float>& CurveMajorValues)
{
#if WITH_EDITOR
	if (!Animation || CurveNames.IsEmpty() || Times.Num() < 2)
	{
		UE_LOG(LogTemp, Error, TEXT("[METAHUMAN-A2F] invalid bulk curve inputs"));
		return false;
	}
	if (CurveMajorValues.Num() != CurveNames.Num() * Times.Num())
	{
		UE_LOG(
			LogTemp,
			Error,
			TEXT("[METAHUMAN-A2F] bulk curve size mismatch names=%d times=%d values=%d"),
			CurveNames.Num(),
			Times.Num(),
			CurveMajorValues.Num());
		return false;
	}
	for (int32 Index = 0; Index < Times.Num(); ++Index)
	{
		if (!FMath::IsFinite(Times[Index]) || (Index > 0 && Times[Index] <= Times[Index - 1]))
		{
			UE_LOG(LogTemp, Error, TEXT("[METAHUMAN-A2F] invalid bulk curve time at %d"), Index);
			return false;
		}
	}

	IAnimationDataController& Controller = Animation->GetController();
	IAnimationDataController::FScopedBracket Bracket(
		Controller,
		LOCTEXT("ApplyA2FCurves", "Apply Audio2Face Curves"),
		false);
	for (int32 CurveIndex = 0; CurveIndex < CurveNames.Num(); ++CurveIndex)
	{
		const FAnimationCurveIdentifier CurveId(
			CurveNames[CurveIndex],
			ERawCurveTrackTypes::RCT_Float);
		if (Animation->GetDataModel()->FindCurve(CurveId) == nullptr)
		{
			if (!Controller.AddCurve(CurveId, 0x00000004, false))
			{
				UE_LOG(
					LogTemp,
					Error,
					TEXT("[METAHUMAN-A2F] failed to add curve %s"),
					*CurveNames[CurveIndex].ToString());
				return false;
			}
		}
		TArray<FRichCurveKey> Keys;
		Keys.Reserve(Times.Num());
		for (int32 KeyIndex = 0; KeyIndex < Times.Num(); ++KeyIndex)
		{
			const float Value = CurveMajorValues[CurveIndex * Times.Num() + KeyIndex];
			if (!FMath::IsFinite(Value))
			{
				UE_LOG(
					LogTemp,
					Error,
					TEXT("[METAHUMAN-A2F] non-finite value curve=%s key=%d"),
					*CurveNames[CurveIndex].ToString(),
					KeyIndex);
				return false;
			}
			Keys.Emplace(Times[KeyIndex], Value);
		}
		if (!Controller.SetCurveKeys(CurveId, Keys, false))
		{
			UE_LOG(
				LogTemp,
				Error,
				TEXT("[METAHUMAN-A2F] failed to set curve %s"),
				*CurveNames[CurveIndex].ToString());
			return false;
		}
	}
	Animation->MarkPackageDirty();
	UE_LOG(
		LogTemp,
		Display,
		TEXT("[METAHUMAN-A2F] bulk curves applied asset=%s curves=%d keys=%d"),
		*Animation->GetPathName(),
		CurveNames.Num(),
		Times.Num());
	return true;
#else
	return false;
#endif
}

bool UKairosDemoEditorLibrary::ApplyHeadRotationsToBodyAnimation(
	UAnimSequence* Animation,
	int32 StartFrame,
	int32 ExpectedFrameRate,
	const TArray<FName>& BoneNames,
	const TArray<float>& BoneWeights,
	const TArray<FRotator>& FrameRotations)
{
#if WITH_EDITOR
	if (!Animation || !Animation->GetSkeleton() || StartFrame < 0 ||
		ExpectedFrameRate <= 0 || BoneNames.IsEmpty() ||
		BoneNames.Num() != BoneWeights.Num() || FrameRotations.Num() < 2)
	{
		UE_LOG(LogTemp, Error, TEXT("[METAHUMAN-A2F] invalid head animation inputs"));
		return false;
	}
	for (int32 BoneIndex = 0; BoneIndex < BoneWeights.Num(); ++BoneIndex)
	{
		if (!FMath::IsFinite(BoneWeights[BoneIndex]) || BoneWeights[BoneIndex] < 0.0f ||
			BoneWeights[BoneIndex] > 1.0f)
		{
			UE_LOG(LogTemp, Error, TEXT("[METAHUMAN-A2F] invalid head bone weight index=%d"), BoneIndex);
			return false;
		}
	}
	for (int32 FrameIndex = 0; FrameIndex < FrameRotations.Num(); ++FrameIndex)
	{
		if (FrameRotations[FrameIndex].ContainsNaN())
		{
			UE_LOG(LogTemp, Error, TEXT("[METAHUMAN-A2F] non-finite head rotation frame=%d"), FrameIndex);
			return false;
		}
	}

	const IAnimationDataModel* Model = Animation->GetDataModel();
	if (!Model)
	{
		UE_LOG(LogTemp, Error, TEXT("[METAHUMAN-A2F] Body animation has no data model"));
		return false;
	}
	const int32 NumberOfKeys = Model->GetNumberOfKeys();
	const FFrameRate FrameRate = Model->GetFrameRate();
	if (NumberOfKeys < StartFrame + FrameRotations.Num() ||
		!FMath::IsNearlyEqual(FrameRate.AsDecimal(), static_cast<double>(ExpectedFrameRate), KINDA_SMALL_NUMBER))
	{
		UE_LOG(
			LogTemp,
			Error,
			TEXT("[METAHUMAN-A2F] Body animation timeline mismatch keys=%d start=%d samples=%d fps=%s"),
			NumberOfKeys,
			StartFrame,
			FrameRotations.Num(),
			*FrameRate.ToPrettyText().ToString());
		return false;
	}

	const FReferenceSkeleton& ReferenceSkeleton = Animation->GetSkeleton()->GetReferenceSkeleton();
	IAnimationDataController& Controller = Animation->GetController();
	IAnimationDataController::FScopedBracket Bracket(
		Controller,
		LOCTEXT("ApplyA2FHeadRotations", "Apply Audio2Face Head Rotations"),
		false);
	for (int32 BoneListIndex = 0; BoneListIndex < BoneNames.Num(); ++BoneListIndex)
	{
		const FName BoneName = BoneNames[BoneListIndex];
		const int32 SkeletonBoneIndex = ReferenceSkeleton.FindBoneIndex(BoneName);
		if (SkeletonBoneIndex == INDEX_NONE)
		{
			UE_LOG(LogTemp, Error, TEXT("[METAHUMAN-A2F] Body skeleton missing bone=%s"), *BoneName.ToString());
			return false;
		}

		TArray<FTransform> BoneTransforms;
		if (Model->IsValidBoneTrackName(BoneName))
		{
			Model->GetBoneTrackTransforms(BoneName, BoneTransforms);
		}
		else
		{
			BoneTransforms.Init(ReferenceSkeleton.GetRefBonePose()[SkeletonBoneIndex], NumberOfKeys);
			if (!Controller.AddBoneCurve(BoneName, false))
			{
				UE_LOG(LogTemp, Error, TEXT("[METAHUMAN-A2F] failed to add Body bone track=%s"), *BoneName.ToString());
				return false;
			}
		}
		if (BoneTransforms.Num() == 1)
		{
			BoneTransforms.Init(BoneTransforms[0], NumberOfKeys);
		}
		if (BoneTransforms.Num() != NumberOfKeys)
		{
			UE_LOG(
				LogTemp,
				Error,
				TEXT("[METAHUMAN-A2F] Body bone track size mismatch bone=%s keys=%d expected=%d"),
				*BoneName.ToString(),
				BoneTransforms.Num(),
				NumberOfKeys);
			return false;
		}

		const float BoneWeight = BoneWeights[BoneListIndex];
		for (int32 MotionFrameIndex = 0; MotionFrameIndex < FrameRotations.Num(); ++MotionFrameIndex)
		{
			const FRotator& Input = FrameRotations[MotionFrameIndex];
			const FQuat Delta = FRotator(
				Input.Pitch * BoneWeight,
				Input.Yaw * BoneWeight,
				Input.Roll * BoneWeight).Quaternion();
			FTransform& BaseTransform = BoneTransforms[StartFrame + MotionFrameIndex];
			BaseTransform.SetRotation((Delta * BaseTransform.GetRotation()).GetNormalized());
		}

		TArray<FVector> PositionalKeys;
		TArray<FQuat> RotationalKeys;
		TArray<FVector> ScalingKeys;
		PositionalKeys.Reserve(NumberOfKeys);
		RotationalKeys.Reserve(NumberOfKeys);
		ScalingKeys.Reserve(NumberOfKeys);
		for (const FTransform& Transform : BoneTransforms)
		{
			PositionalKeys.Add(Transform.GetTranslation());
			RotationalKeys.Add(Transform.GetRotation());
			ScalingKeys.Add(Transform.GetScale3D());
		}
		if (!Controller.SetBoneTrackKeys(
			BoneName,
			PositionalKeys,
			RotationalKeys,
			ScalingKeys,
			false))
		{
			UE_LOG(LogTemp, Error, TEXT("[METAHUMAN-A2F] failed to set Body bone keys=%s"), *BoneName.ToString());
			return false;
		}
	}
	Controller.NotifyPopulated();
	Animation->MarkPackageDirty();
	UE_LOG(
		LogTemp,
		Display,
		TEXT("[METAHUMAN-A2F] baked Body head animation asset=%s bones=%d samples=%d start=%d keys=%d"),
		*Animation->GetPathName(),
		BoneNames.Num(),
		FrameRotations.Num(),
		StartFrame,
		NumberOfKeys);
	return true;
#else
	return false;
#endif
}

TArray<float> UKairosDemoEditorLibrary::GetBodyAnimationBoneRotationDeltas(
	UAnimSequence* Animation,
	int32 StartFrame,
	int32 FrameCount,
	const TArray<FName>& BoneNames)
{
	TArray<float> Result;
#if WITH_EDITOR
	const IAnimationDataModel* Model = Animation ? Animation->GetDataModel() : nullptr;
	if (!Model || StartFrame < 0 || FrameCount < 2 ||
		StartFrame + FrameCount > Model->GetNumberOfKeys() || BoneNames.IsEmpty())
	{
		UE_LOG(LogTemp, Error, TEXT("[METAHUMAN-A2F] invalid Body bone readback inputs"));
		return Result;
	}
	Result.Reserve(BoneNames.Num());
	for (const FName BoneName : BoneNames)
	{
		TArray<FTransform> BoneTransforms;
		if (!Model->IsValidBoneTrackName(BoneName))
		{
			UE_LOG(LogTemp, Error, TEXT("[METAHUMAN-A2F] Body readback missing track=%s"), *BoneName.ToString());
			Result.Reset();
			return Result;
		}
		Model->GetBoneTrackTransforms(BoneName, BoneTransforms);
		if (BoneTransforms.Num() == 1)
		{
			BoneTransforms.Init(BoneTransforms[0], Model->GetNumberOfKeys());
		}
		if (BoneTransforms.Num() != Model->GetNumberOfKeys())
		{
			Result.Reset();
			return Result;
		}
		const FQuat Reference = BoneTransforms[StartFrame].GetRotation();
		float MaximumDeltaDegrees = 0.0f;
		for (int32 Index = StartFrame; Index < StartFrame + FrameCount; ++Index)
		{
			const float DeltaDegrees = FMath::RadiansToDegrees(
				Reference.AngularDistance(BoneTransforms[Index].GetRotation()));
			MaximumDeltaDegrees = FMath::Max(MaximumDeltaDegrees, DeltaDegrees);
		}
		Result.Add(MaximumDeltaDegrees);
	}
#endif
	return Result;
}

#undef LOCTEXT_NAMESPACE
