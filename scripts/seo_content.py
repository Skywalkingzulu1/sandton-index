#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
seo_content.py -- Per-category SEO, Google Business Profile and FAQ content.

One entry per hub group. Each carries:

  gbp_category  the Google Business Profile primary category, using Google's
                own taxonomy. This is the single highest-impact field for
                local pack ranking, so the page has to tell the owner exactly
                which one to pick. Guessing wrong here costs more than any
                on-page work.
  gbp_extra     additional GBP categories, which measurably improve average
                map ranking
  services      the concrete things a business in this category does,
                written as phrases a customer would actually type. These
                become page body copy, so they are real service terms, not
                keyword stuffing
  faqs          questions a real customer asks before choosing. Feeds
                FAQPage schema and an on-page FAQ block
  price_range   GBP price band
  nearby        landmark phrases used to build local, non-generic copy

Rules that shaped this file:
  - No fabricated review counts or star ratings. AggregateRating in
    structured data that is not real is a manual-action risk, and it is the
    one shortcut most often taken on directory pages. It is deliberately
    absent.
  - No invented claims about a business (awards, "best in Sandton", years
    trading). Those are the business's to make once they claim the listing.
  - Coupon/offer markup is never attached to the listed business. It belongs
    to the cross-promotion, not to a sandwich shop.
"""

# Coupon served on every generated page. Cross-promotion to the operator's
# own platform, so it is clearly labelled as a sponsor offer rather than
# something the listed business is selling.
COUPON = {
    "enabled": True,
    "brand": "Doctors on Wheels",
    "offer": "20% off your first online consultation",
    "code": "SANDTON20",
    "url": "https://docsonwheels.co.za/register.html",
    "utm_source": "sandton-index",
    "utm_medium": "referral",
    "utm_campaign": "free-listing",
    "note": "Online or home-visit consultation. New patients only.",
    # Where the module may be placed. Never inside the listed business's own
    # structured data.
    "placement": "footer-module",
}

HUB_SEO = {
    "restaurants-takeaways": {
        "gbp_category": "Restaurant",
        "gbp_extra": ["Takeaway restaurant", "Restaurant",
                      "Breakfast restaurant", "Italian restaurant"],
        "price_range": "R60–R400",
        "services": [
            "Sit-down dining", "Takeaway and collection", "Home delivery",
            "Breakfast and brunch", "Lunch specials", "Private functions",
            "Kids menu", "Vegetarian and vegan options",
        ],
        "faqs": [
            ("Do you take card payments?",
             "Most restaurants in Sandton accept credit and debit cards as "
             "well as cash. Confirm with the venue before a large table."),
            ("Is takeaway available?",
             "Takeaway is common in this area. It is worth calling ahead "
             "during peak hours so your order is ready when you arrive."),
            ("Do you cater for allergies or dietary requirements?",
             "Always tell the kitchen when you order if you have an allergy "
             "or are avoiding gluten, nuts or dairy. Ask for the current "
             "menu rather than relying on a previous visit."),
        ],
        "nearby": ["Sandton City", "Nelson Mandela Square", "Rivonia Road",
                   "Sandton Convention Centre"],
    },
    "supermarkets": {
        "gbp_category": "Supermarket",
        "gbp_extra": ["Grocery store", "Convenience store", "Food store"],
        "price_range": "R20–R500",
        "services": [
            "Fresh produce", "Butchery and meat counter", "Bakery",
            "Dairy and chilled", "Dry goods", "Household essentials",
            "Ready-made meals", "Click and collect",
        ],
        "faqs": [
            ("What time do you open?",
             "Supermarkets in Sandton commonly open between 07:00 and 09:00 "
             "on weekdays, earlier on Saturdays. Check the hours shown above, "
             "and confirm before travelling if you need something early."),
            ("Do you deliver?",
             "Delivery and click-and-collect are common but depend on the "
             "store. Calling the number above is the quickest way to find out "
             "about a delivery radius and minimum order."),
            ("Do you accept card payment?",
             "Yes, most Sandton supermarkets take cards, though some smaller "
             "stores have a minimum spend or a small card surcharge."),
        ],
        "nearby": ["Sandton City", "Marlboro Park", "Rivonia Road",
                   "Sandton Office Park"],
    },
    "convenience-liquor": {
        "gbp_category": "Convenience store",
        "gbp_extra": ["Liquor store", "Beer seller", "Wine shop",
                      "Tobacco shop"],
        "price_range": "R10–R600",
        "services": [
            "Beer, wine and spirits", "Tobacco", "Snacks and cold drinks",
            "ATM and cash withdrawal", "Top-up cards", "Household basics",
            "Takeaway food",
        ],
        "faqs": [
            ("Can I buy alcohol here?",
             "Liquor sales in South Africa are age-restricted. You will need "
             "photo ID, and the limit is per person per day."),
            ("What are your opening hours?",
             "Convenience stores often trade longer than other retailers, "
             "including weekends and public holidays. The hours above are "
             "indicative -- confirm before travelling late."),
            ("Do you have an ATM?",
             "Many stores in this category offer cash withdrawal. Check the "
             "listing above or call ahead if you need cash before banking "
             "hours."),
        ],
        "nearby": ["Sandton CBD", "Rivonia Road", "Marlboro Park",
                   "Sunninghill"],
    },
    "clothing-fashion": {
        "gbp_category": "Clothing store",
        "gbp_extra": ["Women's clothing store", "Men's clothing store",
                      "Shoe store", "Boutique", "Fashion accessories store"],
        "price_range": "R150–R5,000",
        "services": [
            "Women's clothing", "Men's clothing", "Shoes and footwear",
            "Accessories and handbags", "Alterations", "Kids clothing",
            "Sportswear", "Gift and novelty items",
        ],
        "faqs": [
            ("Can clothes be altered on site?",
             "Many stores offer alterations. Ask before you buy how long a "
             "hem or sleeve takes, and whether the fitting can be done while "
             "you wait."),
            ("Do you stock plus and petite sizes?",
             "Stock varies by brand. It is worth calling ahead about a "
             "specific size rather than making a trip across town."),
            ("Can I return an item without a receipt?",
             "South African consumer law requires certain items to be "
             "accepted back within six months with a valid proof of purchase. "
             "Keep your slip."),
        ],
        "nearby": ["Sandton City", "Nelson Mandela Square", "Rivonia Road",
                   "Illovo Boulevard"],
    },
    "beauty-hair": {
        "gbp_category": "Beauty salon",
        "gbp_extra": ["Hair salon", "Barber shop", "Nail salon",
                      "Massage therapist", "Cosmetics store"],
        "price_range": "R100–R2,500",
        "services": [
            "Hair cutting and styling", "Colour and highlights", "Braids and "
            "weaves", "Extensions", "Manicure and pedicure", "Facials and "
            "skincare", "Massage and body treatments", "Makeup",
        ],
        "faqs": [
            ("Do I need an appointment?",
             "Most salons book ahead, especially at weekends. Calling the "
             "number above is faster than waiting to be turned away."),
            ("How often should I come in for a treatment?",
             "It depends on the service and your hair or skin type. A "
             "stylist can give you a realistic schedule rather than a "
             "fixed rule -- ask for one at your first visit."),
            ("What preparation do I need before an appointment?",
             "Arrive with clean, dry hair for most cutting and colour work, "
             "and bring reference photos if you want a specific result."),
        ],
        "nearby": ["Sandton CBD", "Illovo Boulevard", "Rivonia Road",
                   "Sunninghill"],
    },
    "health-wellness": {
        "gbp_category": "Medical clinic",
        "gbp_extra": ["Pharmacy", "Dentist", "Optician", "Physiotherapist",
                      "Wellness centre"],
        "price_range": "R80–R1,500",
        "services": [
            "General consultations", "Prescriptions and dispensing",
            "Chronic condition management", "Screening and diagnostics",
            "Vaccinations", "Physiotherapy and rehabilitation",
            "Optical services", "Health and wellness programmes",
        ],
        "faqs": [
            ("Do I need to book, or can I walk in?",
             "Booking ahead is usually faster, though most practices will see "
             "urgent cases on a walk-in basis. Calling the number above is the "
             "quickest route."),
            ("What should I bring to a first appointment?",
             "Bring your ID, any medical aid details, and a current list of "
             "medication. If you can get earlier records, that avoids repeat "
             "tests."),
            ("Do you accept medical aid?",
             "Acceptance varies by practice and by plan. Ask which schemes are "
             "accepted, and whether a co-payment applies."),
        ],
        "nearby": ["Sandton CBD", "Rivonia Road", "Sandton Office Park",
                   "Bryanston"],
    },
    "hotels-accommodation": {
        "gbp_category": "Hotel",
        "gbp_extra": ["Guest house", "Hostel", "Apartment rental",
                      "Bed and breakfast"],
        "price_range": "R600–R5,000",
        "services": [
            "Overnight accommodation", "Short-stay and day rooms",
            "Conference and meeting space", "Airport transfers",
            "Breakfast and dining", "Wi-Fi and workspace", "Secure parking",
        ],
        "faqs": [
            ("What time is check-in and check-out?",
             "Check-in is commonly from 14:00 and check-out by 10:00, but it "
             "varies. Ask when booking if you need an early arrival or a late "
             "departure."),
            ("Is parking included?",
             "Secure parking is common but sometimes charged separately, "
             "especially close to the Sandton Convention Centre."),
            ("Can I book for same-day use?",
             "Day-use rooms are offered by some properties. Call ahead, as "
             "availability depends on the day."),
        ],
        "nearby": ["Sandton Convention Centre", "Sandton City",
                   "Rivonia Road", "Gautrain station"],
    },
    "home-furniture": {
        "gbp_category": "Furniture store",
        "gbp_extra": ["Home goods store", "Interior design service",
                      "Kitchen and bathroom supplier", "Bedding store"],
        "price_range": "R300–R30,000",
        "services": [
            "Living room and bedroom furniture", "Office and home office",
            "Mattresses and beds", "Dining tables and chairs", "Décor and "
            "accessories", "Curtains and soft furnishings", "Delivery and "
            "assembly", "Interior design advice",
        ],
        "faqs": [
            ("Do you deliver and assemble?",
             "Most furniture stores deliver within the Sandton area, and many "
             "will assemble on delivery. Confirm the delivery fee before you "
             "order."),
            ("Can I see the item before buying?",
             "Showing stock in person is worth the trip for a large purchase, "
             "as finishes and sizes vary more than catalogue photos suggest."),
            ("Do you offer finance?",
             "Many retailers in this category offer monthly instalments. Ask "
             "about the terms and the total cost, not just the monthly "
             "amount."),
        ],
        "nearby": ["Sandton Home", "Rivonia Road", "Marlboro Park",
                   "Woodmead"],
    },
    "doityourself-hardware": {
        "gbp_category": "Hardware store",
        "gbp_extra": ["Home improvement store", "Paint store",
                      "Building supplies store", "Tool shop"],
        "price_range": "R40–R8,000",
        "services": [
            "Tools and equipment", "Paint and coatings", "Plumbing supplies",
            "Electrical supplies", "Building materials", "Garden and outdoor",
            "Safety equipment", "Key cutting and advice",
        ],
        "faqs": [
            ("Do you cut keys?",
             "Most hardware stores offer key cutting. Bring the key or a clear "
             "description of what is needed."),
            ("Can you help me choose the right product?",
             "Staff at a trade counter will usually work out what you need "
             "from a photo or a description of the job, which is faster than "
             "guessing at the shelf."),
            ("Do you deliver to site?",
             "Delivery within the local area is common for heavier materials. "
             "Call with your list to save a trip."),
        ],
        "nearby": ["Marlboro Park", "Sandton Home", "Woodmead",
                   "Rivonia Road"],
    },
    "automotive": {
        "gbp_category": "Auto repair shop",
        "gbp_extra": ["Car dealer", "Tire shop", "Auto parts store",
                      "Car wash", "Vehicle inspection"],
        "price_range": "R250–R900,000",
        "services": [
            "General servicing", "Brakes and suspension", "Engine "
            "diagnostics", "Tyres and wheel alignment", "Battery and "
            "electrical", "Air conditioning", "Accident repairs and panel "
            "beating", "Vehicle inspections",
        ],
        "faqs": [
            ("How long does a service take?",
             "A minor service is commonly half a day, a major service closer "
             "to a full day. Ask for a written estimate including the "
             "expected collection time."),
            ("Should I use OEM or aftermarket parts?",
             "It depends on the vehicle and the work. A good workshop will "
             "explain the trade-off in cost and expected lifespan rather than "
             "just recommending the pricier option."),
            ("Do you offer a courtesy car?",
             "Many workshops in Sandton do. Confirm before booking so you can "
             "plan around it."),
        ],
        "nearby": ["Rivonia Road", "Marlboro Park", "Sandton CBD",
                   "Beyers Naude Square"],
    },
    "professional-services": {
        "gbp_category": "Lawyer",
        "gbp_extra": ["Accountant", "Financial advisor", "Insurance agency",
                      "Real estate agency", "Consulting firm"],
        "price_range": "R400–R150,000",
        "services": [
            "Legal advice and representation", "Contract drafting and review",
            "Company and compliance", "Tax and accounting", "Financial "
            "planning", "Insurance broking", "Property sales and rentals",
            "Business consulting",
        ],
        "faqs": [
            ("How much does a first consultation cost?",
             "Many firms charge for an initial consultation and credit it "
             "against later work. Ask about the rate and the expected total "
             "before instructing."),
            ("Do I need an appointment?",
             "Yes. These firms are usually by appointment, and a short call "
             "beforehand lets them point you to the right person."),
            ("What should I bring to a first meeting?",
             "Any contracts, correspondence or notices you have, plus a clear "
             "note of the outcome you want. Chronology matters more than "
             "detail."),
        ],
        "nearby": ["Rivonia Road", "Sandton CBD", "Sandton Office Park",
                   "Illovo"],
    },
    "banks-financial": {
        "gbp_category": "Bank",
        "gbp_extra": ["Credit union", "Financial institution",
                      "Insurance company", "Investment company"],
        "price_range": "R100–R2,000,000",
        "services": [
            "Current and savings accounts", "Cheque and credit accounts",
            "Loans and financing", "Card services", "Investments", "Insurance",
            "Retirement planning", "Business banking",
        ],
        "faqs": [
            ("What do I need to open an account?",
             "Photo ID and proof of address are the standard requirements. Some "
             "institutions also want proof of income for certain accounts."),
            ("Is there a monthly fee?",
             "Fees vary by account type. Ask for the full schedule, including "
             "what triggers a higher monthly charge."),
            ("Do I need an appointment?",
             "Bookings avoid a wait. Walk-in services are usually available "
             "for simpler transactions."),
        ],
        "nearby": ["Sandton CBD", "Rivonia Road", "Sandton Office Park",
                   "Nelson Mandela Square"],
    },
    "tech-it": {
        "gbp_category": "Computer repair service",
        "gbp_extra": ["Software company", "Telecommunications provider",
                      "IT services company", "Electronics store"],
        "price_range": "R200–R500,000",
        "services": [
            "Managed IT support", "Network and infrastructure", "Cloud and "
            "hosting", "Cybersecurity", "Hardware supply and repair", ""
            "Telecommunications", "Software development", "Data backup and "
            "recovery",
        ],
        "faqs": [
            ("Do you offer on-site support?",
             "Most providers in Sandton do, and remote support is often a "
             "faster first step. Ask which applies to your situation."),
            ("How is support billed?",
             "Commonly per hour, per device, or on a monthly retainer. Ask for "
             "the rate structure and what is included before committing."),
            ("Can you help migrate existing data?",
             "Most can. Confirm who handles the transfer and what happens if "
             "something fails partway through."),
        ],
        "nearby": ["Sandton Office Park", "Rivonia Road", "Sandton CBD",
                   "Gautrain station"],
    },
    "offices-coworking": {
        "gbp_category": "Coworking space",
        "gbp_extra": ["Office supply store", "Real estate agency",
                      "Business centre", "Virtual office provider"],
        "price_range": "R500–R120,000",
        "services": [
            "Serviced offices", "Hot desk and dedicated desks", "Meeting "
            "rooms", "Virtual offices and mail handling", "Reception and "
            "addressing", "Shared kitchen and breakout", "High-speed internet",
            "Parking and access control",
        ],
        "faqs": [
            ("Can I visit before signing?",
             "Yes, and you should. Book a viewing to check noise levels, "
             "parking and the internet at the hours you would actually work."),
            ("What is included in the monthly fee?",
             "It varies widely. Ask specifically about internet, meeting room "
             "credits, printing and whether furniture is included."),
            ("Is a lease or deposit required?",
             "Serviced offices normally need a deposit and a few months' "
             "notice rather than a long lease. Get the notice period in "
             "writing."),
        ],
        "nearby": ["Sandton Office Park", "Rivonia Road", "Sandton CBD",
                   "Melrose Arch"],
    },
    "malls-shopping-centres": {
        "gbp_category": "Shopping mall",
        "gbp_extra": ["Shopping centre", "Retail building", "Market"],
        "price_range": "R50–R5,000",
        "services": [
            "Retail stores", "Food court and restaurants", "Parking",
            "Cinema and entertainment", "Medical and pharmacy tenants",
            "Children's activities", "Beauty and services", "Grocery and "
            "convenience",
        ],
        "faqs": [
            ("What are the trading hours?",
             "Most centres in Sandton trade from around 09:00 to 19:00, later "
             "on Fridays. Individual stores vary, so check for the one you "
             "want specifically."),
            ("Is parking free?",
             "Most offer free customer parking with a time limit. The number "
             "plate goes into a system at the boom gate, so note it down."),
            ("Which stores are open today?",
             "Store hours differ from centre hours. Calling the store "
             "directly is more reliable than the centre's own listing."),
        ],
        "nearby": ["Sandton City", "Nelson Mandela Square",
                   "Sandton Convention Centre", "Rivonia Road"],
    },
    "fitness-sports": {
        "gbp_category": "Gym",
        "gbp_extra": ["Fitness centre", "Sports club", "Yoga studio",
                      "Golf course", "Martial arts school"],
        "price_range": "R250–R3,000",
        "services": [
            "Gym memberships", "Group fitness classes", "Personal training",
            "Yoga and pilates", "Swimming", "Sports coaching", "Sports court "
            "hire", "Recovery and wellness",
        ],
        "faqs": [
            ("Is there a joining fee?",
             "Most facilities charge both a monthly fee and a once-off joining "
             "fee. Ask for the total first-month cost."),
            ("Can I try a class before joining?",
             "A free trial or a day pass is common. Ask what the trial "
             "includes and whether you need to book."),
            ("What are the peak times?",
             "Weekday mornings before 08:00 and weekdays from about 17:00 "
             "are the busiest. Early morning and weekend mornings are usually "
             "quieter."),
        ],
        "nearby": ["Sandton CBD", "Rivonia Road", "Sandton City",
                   "Marlboro Park"],
    },
    "services-home": {
        "gbp_category": "House cleaning service",
        "gbp_extra": ["Dry cleaning service", "Locksmith", "Security service",
                      "Air conditioning contractor", "Moving company",
                      "Pest control service"],
        "price_range": "R150–R25,000",
        "services": [
            "Domestic and office cleaning", "Laundry and dry cleaning",
            "Locksmith and key cutting", "Security systems and monitoring",
            "Air conditioning service", "Pest control", "Storage and "
            "removals", "Handyman and general repairs",
        ],
        "faqs": [
            ("Do I need to be home?",
             "Not for most services, as long as there is safe access. Agree "
             "key or alarm arrangements in advance."),
            ("How is the price calculated?",
             "Often by the hour or by area. A written quote before work starts "
             "is worth asking for on anything larger."),
            ("Are you insured and bonded?",
             "For work in your home, this matters. Ask for the certificate if "
             "you are having electrical, gas or structural work done."),
        ],
        "nearby": ["Sandton CBD", "Illovo", "Rivonia Road", "Woodmead"],
    },
    "education-training": {
        "gbp_category": "Educational institution",
        "gbp_extra": ["Training centre", "Tutoring service", "School",
                      "College"],
        "price_range": "R500–R60,000",
        "services": [
            "Tuition and one-on-one support", "Exam preparation",
            "Corporate training", "Language courses", "Accredited short "
            "courses", "Career training", "Internships and placements",
            "Student accommodation support",
        ],
        "faqs": [
            ("Are classes in person or online?",
             "Most providers offer both. Ask which suits the course before "
             "committing to a fee."),
            ("Is the course accredited?",
             "For a CV, accredited certificates carry real weight. Ask for the "
             "registration number and check it."),
            ("What are the entry requirements?",
             "Varies widely by provider and course. A short call usually "
             "settles it."),
        ],
        "nearby": ["Sandton CBD", "Rivonia Road", "Bryanston",
                   "Sandton Office Park"],
    },
    "pets-animals": {
        "gbp_category": "Pet store",
        "gbp_extra": ["Veterinary care", "Pet supply store", "Pet groomer",
                      "Animal shelter"],
        "price_range": "R80–R3,500",
        "services": [
            "Pet food and supplies", "Veterinary consultations",
            "Vaccinations and deworming", "Grooming", "Boarding and daycare",
            "Puppy training", "Emergency after-hours care", "Pet accessories",
        ],
        "faqs": [
            ("Do I need an appointment for the vet?",
             "For routine visits, booking ahead is wise. Emergency services "
             "are normally handled on a walk-in basis."),
            ("Can I bring my pet in for a same-day visit?",
             "Call the number above. Many practices keep slots for urgent "
             "cases on the day."),
            ("What vaccinations does my pet need?",
             "Core vaccines are given as a series, with boosters. A vet can "
             "tell you exactly where your pet is up to."),
        ],
        "nearby": ["Sandton CBD", "Marlboro Park", "Rivonia Road",
                   "Bryanston"],
    },
    "media-printing": {
        "gbp_category": "Print shop",
        "gbp_extra": ["Book shop", "Stationery store", "Photographer",
                      "Bookstore", "Music store"],
        "price_range": "R50–R20,000",
        "services": [
            "Document printing and copying", "Large format printing",
            "Business cards and stationery", "Binding and finishing",
            "Book sales", "School and office supplies", "Photography and "
            "video", "Musical instruments and equipment",
        ],
        "faqs": [
            ("Can you print and finish same day?",
             "Most print shops can for standard jobs. Larger runs take longer, "
             "so call ahead with your quantity and deadline."),
            ("What file formats do you accept?",
             "PDF is most reliable, but common design formats usually work. "
             "Sending a PDF avoids font and layout surprises."),
            ("Do you deliver to offices?",
             "Business delivery is common, often on a weekly run. Ask about "
             "the schedule and minimum order."),
        ],
        "nearby": ["Sandton CBD", "Rivonia Road", "Sandton Office Park",
                   "Illovo"],
    },
    "travel-tourism": {
        "gbp_category": "Travel agency",
        "gbp_extra": ["Tour operator", "Tourist information centre",
                      "Accommodation booking service"],
        "price_range": "R500–R150,000",
        "services": [
            "Flight and accommodation booking", "Safari and tour packages",
            "Car hire and transfers", "Travel insurance", "Corporate travel",
            "Visa and passport support", "Group travel", "Staycations",
        ],
        "faqs": [
            ("Do you charge a booking fee?",
             "Many agencies earn commission from suppliers and charge nothing "
             "to the client, but not all. Ask before you book."),
            ("Can you book just flights?",
             "Yes. A flight-only booking is routine, and often the quickest "
             "option if you know your dates."),
            ("Do you handle corporate travel?",
             "Most do, on an account basis. Ask about monthly invoicing and "
             "reporting if your company needs it."),
        ],
        "nearby": ["OR Tambo Airport", "Sandton CBD", "Rivonia Road",
                   "Rosebank"],
    },
    "auctions-pawn": {
        "gbp_category": "Pawn shop",
        "gbp_extra": ["Auction house", "Second hand store", "Jeweller",
                      "Cash buyer"],
        "price_range": "R100–R500,000",
        "services": [
            "Pawn loans", "Gold and diamond buying", "Second hand goods",
            "Auction sales", "Valuations", "Consignment sales",
            "Trade-in and cash purchase",
        ],
        "faqs": [
            ("What can I pawn?",
             "Most pawn shops take jewellery, electronics, tools and certain "
             "vehicles. Call with the item and they will tell you quickly "
             "whether it qualifies."),
            ("How is the loan repaid?",
             "Typically you buy the item back at the same price by the due "
             "date. Ask about the interest and grace period up front."),
            ("Is my valuation final?",
             "No. A valuation is an offer based on what the item will resell "
             "for, not a resale price."),
        ],
        "nearby": ["Sandton CBD", "Rivonia Road", "Marlboro Park",
                   "Illovo"],
    },
    "cannabis": {
        "gbp_category": "Cannabis store",
        "gbp_extra": ["Health and wellness shop", "Vapor shop"],
        "price_range": "R100–R1,500",
        "services": [
            "Flower and pre-rolls", "Concentrates and extracts", "Vape "
            "products", "Accessories", "CBD products", "Sourcing questions",
        ],
        "faqs": [
            ("What do I need to buy?",
             "You must be 18 or older and have valid photo ID. You cannot buy "
             "for someone else."),
            ("Can I smoke on site?",
             "Almost never. Products are for off-site use, and smoking on the "
             "premises is generally prohibited."),
            ("What are the legal limits?",
             "South African law sets daily per-person limits. The shop can "
             "explain them and you can always check current regulations "
             "yourself."),
        ],
        "nearby": ["Sandton CBD", "Rivonia Road", "Sunninghill", "Illovo"],
    },
    "other": {
        "gbp_category": "Establishment",
        "gbp_extra": ["General business", "Point of interest establishment"],
        "price_range": "R50–R20,000",
        "services": [
            "General enquiries", "Product and service availability",
            "Opening hours and availability", "Bookings and quotations",
        ],
        "faqs": [
            ("How do I confirm what I need?",
             "Call the number above. For a business that does not fit a "
             "standard category, a short conversation is the fastest route."),
            ("Do I need an appointment?",
             "It depends on what you need. Calling ahead saves a wasted trip."),
        ],
        "nearby": ["Sandton CBD", "Rivonia Road", "Illovo", "Woodmead"],
    },
}

# Fallback used when a hub has no entry, so a new hub can never crash a build.
DEFAULT_SEO = HUB_SEO["other"]


def seo_for(hub_slug):
    return HUB_SEO.get(hub_slug, DEFAULT_SEO)


def coupon_url():
    """UTM-tagged consultation link for the cross-promotion."""
    c = COUPON
    return (f"{c['url']}?utm_source={c['utm_source']}"
            f"&utm_medium={c['utm_medium']}&utm_campaign={c['utm_campaign']}"
            f"&utm_content={c['code']}")


# AggregateRating is intentionally never emitted. Inventing a rating for a
# business that has not claimed its listing is both a factual claim you cannot
# support and a manual-action risk on the whole domain.
NO_AGGREGATE_RATING = True
