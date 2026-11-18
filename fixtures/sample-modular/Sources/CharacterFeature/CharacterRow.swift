import Models

public struct CharacterRow: Equatable {
    public let title: String

    public init(character: Character) {
        title = character.displayName
    }
}
