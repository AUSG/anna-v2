class Member:
    def __init__(self, kor_name: str, eng_name: str, email: str, phone: str, school_name_or_company_name: str):
        self.kor_name = kor_name
        self.eng_name = eng_name
        self.email = email
        self.phone = phone
        self.school_name_or_company_name = school_name_or_company_name

    def __str__(self) -> str:
        return f"[Member] {self.kor_name} | {self.eng_name} | {self.email} | {self.phone} | {self.school_name_or_company_name}"

    def __eq__(self, obj):
        return isinstance(obj, Member) and \
               self.kor_name == obj.kor_name and \
               self.eng_name == obj.eng_name and \
               self.email == obj.email and \
               self.phone == obj.phone and \
               self.school_name_or_company_name == obj.school_name_or_company_name
